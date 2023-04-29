import decimal
from decimal import Decimal
import requests
import base64
import datetime
import hashlib
from django.shortcuts import render, redirect, get_object_or_404
from .forms import UserRegistrationForm, CheckoutForm, ProfileForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Product, Category, Cart, CartItem, Profile
from django.db.models import Subquery, OuterRef, Sum
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your views here.

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'auth/register.html', {'form': form})

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, 'You have been logged in.')
            return redirect('home')
        else:
            messages.error(request, 'Invalid login credentials.')
    return render(request, 'auth/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')

@login_required
def profile(request):
    user = request.user
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile')
    else:
        form = ProfileForm(instance=user.profile)
    return render(request, 'profile.html', {'form': form, 'user': user})

def product_list(request):
    category_slug = request.GET.get('category')
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = Product.objects.filter(category=category)
    else:
        products = Product.objects.all()

    categories = Category.objects.all()
    context = {
        'products': products,
        'categories': categories,
        'current_category': category_slug,
    }
    return render(request, 'home.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    context = {
        'product': product,
    }
    return render(request, 'product_detail.html', context)

#cart

def cart_view(request):
    cart = Cart.objects.filter(user=request.user).first()
    if not cart:
        cart = Cart.objects.create(user=request.user)
    cart_items = cart.cartitem_set.all()
    subtotal = sum(item.get_total_cost() for item in cart_items)
    tax = decimal.Decimal('0.025') * subtotal
    tax = tax.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP)
    total = subtotal + tax
    total = total.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP)
    context = {
        'cart_items': cart_items,
        'cart': cart,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
    }
    return render(request, 'shopping_cart.html', context)

def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = Cart.objects.filter(user=request.user).first()
    if not cart:
        cart = Cart.objects.create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    cart_item.quantity += 1
    cart_item.save()
    messages.success(request, 'Product added to cart.')
    return redirect('cart_view')

def remove_from_cart(request, cart_item_id):
    cart_item = get_object_or_404(CartItem, id=cart_item_id)
    cart_item.delete()
    messages.success(request, 'Product removed from cart.')
    return redirect('cart_view')

def update_cart(request):
    if request.method == 'POST':
        cart_items = request.POST.getlist('cart_item')
        quantities = request.POST.getlist('quantity')
        for i in range(len(cart_items)):
            cart_item = CartItem.objects.get(id=cart_items[i])
            cart_item.quantity = quantities[i]
            cart_item.save()
        messages.success(request, 'Cart updated.')
        return redirect('cart_view')

#MPESA CONFIGURATION

def get_mpesa_access_token():
    """
    Generates an access token for the M-PESA API.
    """
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_SECRET_KEY

    api_key = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()

    # Make a request to the authentication endpoint to generate the access token
    response = requests.get(
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {api_key}"}
    )

    if response.status_code == 200:
        return response.json()["access_token"]
    raise Exception("Failed to generate access token for M-PESA API")


def get_mpesa_password():
    """
    Generates the password required for the M-PESA API request.
    """
    # Get the timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    plaintext = f"{settings.MPESA_BUSINESS_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"

    password = hashlib.sha1(plaintext.encode()).hexdigest()
    return password


def get_mpesa_timestamp():
    """
    Generates the timestamp required for the M-PESA API request.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return timestamp


@login_required
def checkout(request):
    try:
        cart = Cart.objects.get(user=request.user)
    except Cart.DoesNotExist:
        return redirect('cart_view')
    cart_items = cart.cartitem_set.all()
    subtotal = sum(item.get_total_cost() for item in cart_items)
    tax = round(subtotal * Decimal(0.025), 2)
    total = subtotal + tax

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            # Save the contact information to the user's profile
            profile = request.user.profile
            profile.phone_number = form.cleaned_data['phone_number']
            profile.save()

            # Create the Mpesa transaction
            access_token = get_mpesa_access_token()
            url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "BusinessShortCode": settings.MPESA_BUSINESS_SHORTCODE,
                "Password": get_mpesa_password(),
                "Timestamp": get_mpesa_timestamp(),
                "TransactionType": "CustomerPayBillOnline",
                "Amount": str(total),
                "PartyA": str(profile.phone_number),
                "PartyB": settings.MPESA_BUSINESS_SHORTCODE,
                "PhoneNumber": str(profile.phone_number),
                "CallBackURL": f"{settings.BASE_URL}/mpesa/callback",
                "AccountReference": "Shopping Cart",
                "TransactionDesc": "Shopping Cart Payment"
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                # Redirect the user to the Mpesa payment page
                checkout_request_id = response.json()["CheckoutRequestID"]
                return redirect(f"https://sandbox.safaricom.co.ke/mpesa/stkpush?checkoutRequestID={checkout_request_id}&merchantID={settings.MPESA_BUSINESS_SHORTCODE}&phoneNumber={profile.phone_number}&amount={total}&mpesaPublicKey={settings.MPESA_PUBLIC_KEY}&mpesaSecret={settings.MPESA_SECRET_KEY}&callBackURL={settings.BASE_URL}/mpesa/callback")
            else:
                messages.error(request, "Failed to initiate Mpesa payment.")
                return redirect('cart_view')
    else:
        form = CheckoutForm()

    return render(request, 'checkout.html', {'cart_items': cart_items, 'subtotal': subtotal, 'tax': tax, 'total': total, 'form': form})


@csrf_exempt
def mpesa_callback(request):
    # Get the Mpesa response data
    response = request.body.decode('utf-8')
    data = json.loads(response)

    # Update the order status and transaction code
    order = Order.objects.filter(user=request.user).last()
    if order:
        order.status = data['Body']['stkCallback']['ResultCode'] == 0 and 'shipped' or 'processing'
        order.transaction_code = data['Body']['stkCallback']['CheckoutRequestID']
        order.save()

    return HttpResponse(status=200)