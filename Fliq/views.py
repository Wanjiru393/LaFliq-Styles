import decimal
from decimal import Decimal
import requests
from requests.auth import HTTPBasicAuth
import base64
import time
import datetime
import hashlib
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from .forms import UserRegistrationForm, CheckoutForm, ProfileForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Product, Category, Cart, CartItem, Profile, Order
from django.db.models import Subquery, OuterRef, Sum
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models.signals import post_save
from django.dispatch import receiver

from .utils import MpesaGateWay

cl = MpesaGateWay()

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
        form = CheckoutForm(request.POST or None)
        if form.is_valid():
            # Save the contact information to the user's profile
            profile = request.user.profile
            profile.phone_number = form.cleaned_data['phone_number']
            profile.save()
            callback_url = "http://pos.pos.ocratsystems.co.ke/callback/"
            account_reference = "LaFliq"
            transaction_description = "Payment"

            # Create the Mpesa transaction
            response = cl.stk_push(phone_number=profile.phone_number, amount=int(total), callback_url=callback_url, account_reference=account_reference, transaction_desc=transaction_description)
            
            return HttpResponse(response)
            
            
        else:
            errors = form.errors

            print(errors)
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