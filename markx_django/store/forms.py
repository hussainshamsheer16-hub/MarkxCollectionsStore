from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
import re

from .models import BulkRequest, Comment, ContactMessage, Coupon, CustomRequest, Order, Review, GiftCard, ReferralCode

TEXT = {"class": ""}


class StyledForm(forms.ModelForm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            f.widget.attrs.setdefault("placeholder", f.label)


def normalize_pakistani_mobile(value):
    compact = re.sub(r"[\s()-]", "", value or "")
    if re.fullmatch(r"03\d{9}", compact):
        return compact
    if re.fullmatch(r"\+923\d{9}", compact):
        return "0" + compact[3:]
    raise ValidationError("Enter a Pakistani mobile number as 03XXXXXXXXX or +923XXXXXXXXX.")


class PakistaniPhoneFormMixin:
    def clean_phone(self):
        value = self.cleaned_data.get("phone", "")
        if not value and not self.fields["phone"].required:
            return ""
        return normalize_pakistani_mobile(value)


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            matching_users = list(get_user_model()._default_manager.filter(email__iexact=email)[:2])
            if len(matching_users) == 1:
                self.cleaned_data["username"] = matching_users[0].get_username()
        return super().clean()


class CheckoutForm(PakistaniPhoneFormMixin, StyledForm):
    email = forms.EmailField(required=True, label="Email address")
    promo_code = forms.CharField(required=False, max_length=32, label="Promo code")
    otp_code = forms.CharField(required=False, max_length=6, label="Phone verification code")
    gift_card_code = forms.CharField(required=False, max_length=32, label="Gift card code")
    points_to_redeem = forms.IntegerField(required=False, min_value=0, label="Loyalty points to redeem", initial=0)

    class Meta:
        model = Order
        fields = ["full_name", "phone", "email", "address", "city", "notes", "payment_method"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 2}), "payment_method": forms.RadioSelect}
        labels = {"full_name": "Full name", "phone": "Phone (03XX XXXXXXX)", "address": "Delivery address", "city": "City", "notes": "Order notes (optional)"}

    def clean_promo_code(self):
        code = self.cleaned_data.get("promo_code", "").strip().upper()
        if not code:
            return ""
        coupon = Coupon.objects.filter(code__iexact=code).first()
        if not coupon or not coupon.is_usable:
            raise forms.ValidationError("That promo code is invalid, expired, or already used.")
        return coupon.code

    def clean_gift_card_code(self):
        code = self.cleaned_data.get("gift_card_code", "").strip().upper()
        if code and not GiftCard.objects.filter(code=code, active=True, balance__gt=0).exists():
            raise forms.ValidationError("This gift card is invalid or has no remaining balance.")
        return code


class CustomForm(PakistaniPhoneFormMixin, StyledForm):
    class Meta:
        model = CustomRequest
        fields = ["name", "phone", "email", "tshirt_type", "color", "size", "quantity", "placement", "custom_text", "design_file", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class BulkForm(PakistaniPhoneFormMixin, StyledForm):
    class Meta:
        model = BulkRequest
        fields = ["organization", "contact_person", "phone", "email", "order_type", "tshirt_type", "printing_type", "quantity_range", "logo", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class ContactForm(PakistaniPhoneFormMixin, StyledForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


class CommentForm(StyledForm):
    class Meta:
        model = Comment
        fields = ("name", "message")
        labels = {"message": "Your comment"}
        widgets = {"message": forms.Textarea(attrs={"rows": 5, "maxlength": 600})}


class AccountCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email address")
    referral_code = forms.CharField(required=False, max_length=20, label="Referral code")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username"
        self.fields["username"].help_text = ""
        self.fields["password1"].label = "Password"
        self.fields["password1"].help_text = "Use at least 8 characters."
        self.fields["password2"].label = "Confirm password"
        for field in self.fields.values():
            field.widget.attrs.setdefault("placeholder", field.label)

    def clean_referral_code(self):
        code = self.cleaned_data.get("referral_code", "").strip().upper()
        if code:
            referral = ReferralCode.objects.select_related("owner").filter(code=code).first()
            if not referral:
                raise forms.ValidationError("Referral code was not found.")
            email = self.cleaned_data.get("email", "").strip().casefold()
            if email and email == referral.owner.email.casefold():
                raise forms.ValidationError("You cannot refer yourself.")
        return code


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email")
        labels = {"first_name": "First name", "last_name": "Last name", "email": "Email address"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("placeholder", field.label)


class TrackOrderForm(PakistaniPhoneFormMixin, forms.Form):
    order_number = forms.CharField(max_length=20, label="Order number")
    phone = forms.CharField(max_length=30, label="Phone number", widget=forms.TextInput(attrs={"autocomplete": "tel"}))


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(value, f"{value} / 5") for value in range(1, 6)], coerce=int,
        label="Your rating",
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "maxlength": 2000})}
