import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from .models import WiFiPackage, PaymentTransaction
from django_daraja.mpesa.core import MpesaClient
from django.http import HttpResponse

def captive_login(request):
    if request.user.is_authenticated:
        return redirect('packages')

    if request.method == 'POST':
        # Assuming the username is the phone number
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        user = authenticate(request, username=phone, password=password)
        if user:
            login(request, user)
            
            if request.htmx:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('packages')
                return response
                
            return redirect('packages')
        else:
            context = {'error': 'Invalid credentials', 'phone': phone}
            if request.htmx:
                return render(request, 'captive_portal/partials/login_form.html', context)
            return render(request, 'captive_portal/login.html', context)
    return render(request, 'captive_portal/login.html')


def captive_signup(request):
    if request.user.is_authenticated:
        return redirect('packages')

    User = get_user_model()
    context = {}

    if request.method == 'POST':
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        context['phone'] = phone

        # NOTE: The default OpenWISP user model uses 'email' as the username field for
        # authentication. The existing login form appears to use a phone number.
        # This signup logic assumes the phone number is stored in the 'username' field
        # and that a custom authentication backend might be configured to check it.

        if password != confirm_password:
            context['error'] = "Passwords do not match."
        elif User.objects.filter(username=phone).exists():
            context['error'] = "Phone number already registered."
        else:
            try:
                # The openwisp_users.User model also requires a unique email.
                # We'll generate a placeholder email from the phone number.
                email = f"{phone}@captive-portal.local"
                if User.objects.filter(email=email).exists():
                    context['error'] = "An account associated with this phone number already exists."
                else:
                    user = User.objects.create_user(username=phone, email=email, password=password)
                    login(request, user)

                    if request.htmx:
                        response = HttpResponse()
                        response['HX-Redirect'] = reverse('packages')
                        return response
                    return redirect('packages')
            except Exception:
                context['error'] = "Could not create account. Please try again."

        # If we are here, it's a POST with an error, render the partial
        return render(request, 'captive_portal/partials/signup_form.html', context)

    # For a GET request, return the signup form.
    # This requires a 'captive_portal/signup.html' template for non-HTMX requests.
    return render(request, 'captive_portal/partials/signup_form.html', context)

@login_required
def package_list(request):
    packages = WiFiPackage.objects.all()
    return render(request, 'captive_portal/packages.html', {'packages': packages})

@login_required
def initiate_payment(request, package_id):
    package = get_object_or_404(WiFiPackage, id=package_id)
    client = MpesaClient()
    
    # Assuming the username is the phone number
    phone_number = request.user.username 
    amount = int(package.price)
    account_reference = f"WIFI_{request.user.id}"
    transaction_desc = f"Payment for {package.name}"
    # Ensure you replace this with your actual domain/callback
    callback_url = request.build_absolute_uri(reverse('mpesa_callback'))
    
    try:
        # Initiate STK Push
        response = client.stk_push(phone_number, amount, account_reference, transaction_desc, callback_url)
        
        # Attempt to get CheckoutRequestID from response (structure depends on django-daraja version)
        checkout_request_id = getattr(response, 'checkout_request_id', '')
        if not checkout_request_id and hasattr(response, 'json'):
             checkout_request_id = response.json().get('CheckoutRequestID', '')
        
        # Create transaction record
        PaymentTransaction.objects.create(
            user=request.user,
            package=package,
            phone_number=phone_number,
            amount=amount,
            checkout_request_id=checkout_request_id,
            status='PENDING'
        )
        
        return HttpResponse(f"<div class='alert alert-success'>STK Push sent to {phone_number}. Please complete payment.</div>")
    except Exception as e:
        return HttpResponse(f"<div class='alert alert-danger'>Error initiating payment: {str(e)}</div>")

@csrf_exempt
def mpesa_callback(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            stk_callback = data.get('Body', {}).get('stkCallback', {})
            result_code = stk_callback.get('ResultCode')
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            
            transaction = PaymentTransaction.objects.filter(checkout_request_id=checkout_request_id).first()
            
            if transaction:
                if result_code == 0:
                    metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                    receipt_number = next((item.get('Value') for item in metadata if item.get('Name') == 'MpesaReceiptNumber'), None)
                    
                    transaction.status = 'COMPLETED'
                    transaction.mpesa_receipt_number = receipt_number
                    transaction.save()
                    
                    # Activate User in OpenWISP Radius
                    try:
                        from openwisp_radius.models import RadiusUserGroup
                        RadiusUserGroup.objects.get_or_create(
                            user=transaction.user, 
                            group_name=transaction.package.radius_group_name
                        )
                    except ImportError:
                        pass # Handle if openwisp_radius is not installed
                else:
                    transaction.status = 'FAILED'
                    transaction.save()
        except Exception:
            pass
            
    return HttpResponse("Success")