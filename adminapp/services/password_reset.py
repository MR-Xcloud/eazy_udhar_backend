import secrets

from customerapp.email_otp import postmark_configured, send_password_reset_email

ACCOUNT_PROFILES = {
    'seller': {
        'account_label': 'EazyUdhar seller app',
        'product_name': 'EazyUdhar Seller',
    },
    'customer': {
        'account_label': 'EazyUdhar customer app',
        'product_name': 'EazyUdhar',
    },
    'admin': {
        'account_label': 'EazyUdhar admin panel',
        'product_name': 'EazyUdhar Admin',
    },
}


def _parse_send_email(value):
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ('0', 'false', 'no', 'off')


def reset_user_password(*, user, account_type, display_name, send_email=True, password=None):
    """
    Set or reset a user password for admin support flows.
    If password is provided, that value is saved. Otherwise a random password is generated.
    When send_email=True, emails the password (not returned in the API unless auto-generated).
    When send_email=False with an auto-generated password, returns temporary_password once.
    Password is only saved after a successful email when send_email=True.
    """
    profile = ACCOUNT_PROFILES.get(account_type, ACCOUNT_PROFILES['customer'])
    email = (getattr(user, 'email', '') or '').strip().lower()
    send_email = _parse_send_email(send_email)
    admin_set = password is not None and str(password).strip() != ''

    if admin_set:
        new_password = str(password).strip()
        if len(new_password) < 8:
            return False, {
                'detail': 'Password must be at least 8 characters.',
                'code': 'invalid_password',
            }
    else:
        new_password = secrets.token_urlsafe(12)

    if send_email and not email:
        return False, {
            'detail': 'This account has no email address. Add an email before emailing the password.',
            'delivery': {'email': {'sent': False, 'to': '', 'error': 'missing_email'}},
        }

    if send_email and not postmark_configured():
        return False, {
            'detail': 'Email is not configured on the server. Password was not changed.',
            'delivery': {
                'email': {
                    'sent': False,
                    'to': email,
                    'error': 'email_not_configured',
                }
            },
        }

    delivery = {'email': {'sent': False, 'skipped': not send_email}}

    if send_email:
        delivery['email'] = send_password_reset_email(
            to_email=email,
            user_name=display_name or email,
            temp_password=new_password,
            account_label=profile['account_label'],
            product_name=profile['product_name'],
        )
        if not delivery['email'].get('sent'):
            return False, {
                'detail': 'Could not deliver the password reset email. Password was not changed.',
                'delivery': delivery,
            }

    user.set_password(new_password)
    user.save(update_fields=['password'])

    if send_email:
        masked = _mask_email(email)
        if admin_set:
            message = (
                f'The new password has been saved and emailed to {masked}. '
                'Ask the user to check their inbox and spam folder.'
            )
        else:
            message = (
                f'A new temporary password has been emailed to {masked}. '
                'Ask the user to check their inbox and spam folder.'
            )
    elif admin_set:
        message = 'Password updated. Share it with the user by phone or WhatsApp.'
    else:
        message = (
            'Password has been reset. Share the temporary password with the user securely — '
            'it is shown once in this admin panel only.'
        )

    payload = {
        'message': message,
        'delivery': delivery,
    }
    if not send_email and not admin_set:
        payload['temporary_password'] = new_password

    return True, payload


def _mask_email(email):
    """Partially mask email for admin UI, e.g. a***@yopmail.com."""
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        shown = '*'
    else:
        shown = f'{local[0]}***'
    return f'{shown}@{domain}'
