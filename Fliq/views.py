from django.shortcuts import render, redirect, get_object_or_404
from .forms import UserRegistrationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import Product, Category, Cart, CartItem
import decimal

# Create your views here.

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'auth/register.html', {'form': form})

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

from django.db.models import Subquery, OuterRef, Sum


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