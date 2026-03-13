import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from .models import WiFiPackage, PaymentTransaction
from django.conf import settings
from django_daraja.mpesa.core import MpesaClient
from django.http import HttpResponse

def captive_login(request):
    if request.user.is_authenticated:
        return redirect('packages')

    if request.method == 'POST':
        # Assuming the username is the phone number
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        user = authenticate(request, phone_number=phone, password=password)
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

    # For GET requests
    context = {}
    if request.htmx:
        # If an HTMX GET request asks for the login page, send only the partial form.
        return render(request, 'captive_portal/partials/login_form.html', context)
    return render(request, 'captive_portal/login.html', context)


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
        
        if password != confirm_password:
            context['error'] = "Passwords do not match."
        elif not phone or not password:
            context['error'] = "Phone number and password are required."
        elif User.objects.filter(phone_number=phone).exists():
            context['error'] = "Phone number already registered."
        else:
            try:
                user = User.objects.create_user(phone_number=phone, password=password)
                login(request, user)
                if request.htmx:
                    response = HttpResponse()
                    response['HX-Redirect'] = reverse('packages')
                    return response
                return redirect('packages')
            except Exception:
                context['error'] = "Could not create account. Please try again."

        # If we are here, it's a POST with an error, render the partial
        if request.htmx:
            return render(request, 'captive_portal/partials/signup_form.html', context)
        return render(request, 'captive_portal/signup.html', context)

    # For GET requests
    if request.htmx:
        # If an HTMX GET request asks for the signup page, send only the partial form.
        return render(request, 'captive_portal/partials/signup_form.html', context)
    return render(request, 'captive_portal/signup.html', context)

def captive_reset_password(request):
    if request.user.is_authenticated:
        return redirect('packages')
    
    context = {}
    if request.method == 'POST':
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        context['phone'] = phone
        
        User = get_user_model()
        
        if password != confirm_password:
            context['error'] = "Passwords do not match."
        elif not phone or not password:
             context['error'] = "Phone number and password are required."
        else:
            try:
                user = User.objects.get(phone_number=phone)
                user.set_password(password)
                user.save()
                context['success'] = "Password reset successfully. Please login."
            except User.DoesNotExist:
                context['error'] = "Account with this phone number not found."
        
        if request.htmx:
            return render(request, 'captive_portal/partials/reset_password_form.html', context)
        return render(request, 'captive_portal/reset_password.html', context)

    if request.htmx:
        return render(request, 'captive_portal/partials/reset_password_form.html', context)
    return render(request, 'captive_portal/reset_password.html', context)

def package_list(request):
    packages = WiFiPackage.objects.all()
    context = {'packages': packages}
    if request.htmx:
        return render(request, 'captive_portal/partials/package_list.html', context)
    return render(request, 'captive_portal/packages.html', context)

def initiate_payment(request, package_id):
    # Handle authentication manually to support HTMX redirects
    if not request.user.is_authenticated:
        if request.htmx:
            response = HttpResponse()
            response['HX-Redirect'] = reverse('captive_login')
            return response
        return redirect('captive_login')

    # Ensure this view, which performs a state change, only accepts POST requests.
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    package = get_object_or_404(WiFiPackage, id=package_id)
    user = request.user

    # Find an existing initiated transaction or create a new one to avoid duplicates
    transaction, created = PaymentTransaction.objects.get_or_create(
        user=user,
        package=package,
        status='INITIATED',
        defaults={
            'phone_number': user.phone_number,
            'amount': package.price,
            'account_reference': f"{settings.MPESA_ACCOUNT_PREFIX}-{package.id}-{user.id}-{uuid.uuid4().hex[:8].upper()}"
        }
    )

    # Return a partial with payment instructions for Paybill
    paybill = settings.MPESA_PAYBILL_NUMBER
    instructions_html = f"""
    <div class='alert alert-info'>
        <h5>Complete Payment via M-Pesa</h5>
        <p>1. Go to your M-Pesa menu.</p>
        <p>2. Select 'Lipa na M-Pesa'.</p>
        <p>3. Select 'Pay Bill'.</p>
        <p>4. Enter Business No: <strong>{paybill}</strong></p>
        <p>5. Enter Account No: <strong>{transaction.account_reference}</strong></p>
        <p>6. Enter Amount: <strong>KES {transaction.amount}</strong></p>
        <p>7. Enter your M-Pesa PIN and confirm.</p>
        <hr>
        <p>We will automatically activate your package once we receive the payment confirmation.</p>
    </div>
    """
    return HttpResponse(instructions_html)

@csrf_exempt
def mpesa_callback(request):
    if request.method == 'POST':
        try:
            # This is now a C2B confirmation callback, not STK Push
            data = json.loads(request.body)

            # Extract relevant data from C2B payload
            account_reference = data.get('BillRefNumber')
            transaction_id = data.get('TransID')
            amount_paid = data.get('TransAmount')

            if not all([account_reference, transaction_id, amount_paid]):
                # Invalid payload, log it and return
                return HttpResponse("Success") # Still return success to M-Pesa

            # Find the initiated transaction using the account reference
            transaction = PaymentTransaction.objects.filter(account_reference=account_reference).first()
            
            if transaction:
                # Basic validation
                if float(amount_paid) < float(transaction.amount):
                    transaction.status = 'UNDERPAID'
                    transaction.save()
                    # TODO: Log this event for admin review
                    return HttpResponse("Success")

                transaction.status = 'COMPLETED'
                transaction.mpesa_receipt_number = transaction_id
                transaction.save()
                
                # --- OpenWISP Integration: Activate Package ---
                try:
                    from openwisp_radius.models import RadiusUserGroup
                    # To ensure a user has only one package, remove old ones first
                    RadiusUserGroup.objects.filter(user=transaction.user).delete()
                    # Assign the new package group
                    RadiusUserGroup.objects.get_or_create(
                        user=transaction.user, 
                        groupname=transaction.package.radius_group_name
                    )
                except ImportError:
                    # TODO: Log that openwisp_radius is not installed or model is not found
                    pass 
                except Exception as e:
                    # TODO: Log the error during radius activation
                    pass
            else:
                # A payment was received but we couldn't find a matching transaction
                # TODO: Log this for review
                pass
        except Exception as e:
            # TODO: Log the exception
            pass
            
    return HttpResponse("Success")