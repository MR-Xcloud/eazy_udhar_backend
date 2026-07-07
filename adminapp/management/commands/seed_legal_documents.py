from datetime import date

from django.core.management.base import BaseCommand

from adminapp.models import LegalDocument


PRIVACY_POLICY_BODY = """\
<h2>Introduction</h2>
<p>EasyUdhar ("we", "our", or "us") respects your privacy. This Privacy Policy explains how we collect, use, and protect your information when you use the EasyUdhar mobile application and related services.</p>

<h2>Information We Collect</h2>
<ul>
<li><strong>Account information:</strong> name, phone number, email address, and business details you provide during registration.</li>
<li><strong>Transaction data:</strong> credit, payment, and ledger records between sellers and customers.</li>
<li><strong>Device information:</strong> push notification tokens and basic device metadata for app functionality.</li>
</ul>

<h2>How We Use Your Information</h2>
<ul>
<li>To provide and operate the EasyUdhar service.</li>
<li>To send payment reminders, notifications, and account-related messages.</li>
<li>To improve security, prevent fraud, and comply with legal obligations.</li>
</ul>

<h2>Data Sharing</h2>
<p>We do not sell your personal data. Information is shared only with linked shops/customers as required for ledger operations, payment processing partners (such as Razorpay), and SMS/email providers needed to deliver the service.</p>

<h2>Your Choices</h2>
<p>You can control visibility of your phone number and email in profile privacy settings. You may contact us to request account deletion or data correction.</p>

<h2>Contact</h2>
<p>For privacy-related questions, email <strong>support@easyudhar.com</strong>.</p>
"""

TERMS_OF_SERVICE_BODY = """\
<h2>Acceptance of Terms</h2>
<p>By creating an account or using EasyUdhar, you agree to these Terms of Service. If you do not agree, please do not use the app.</p>

<h2>Service Description</h2>
<p>EasyUdhar provides digital khata (ledger), payment tracking, reminders, and related tools for sellers and customers. We may update features from time to time.</p>

<h2>User Responsibilities</h2>
<ul>
<li>Provide accurate account and business information.</li>
<li>Keep login credentials secure and notify us of unauthorized access.</li>
<li>Use the platform lawfully and do not harass, defraud, or misuse other users.</li>
</ul>

<h2>Payments</h2>
<p>Online payments are processed through third-party payment providers. EasyUdhar is not responsible for bank or UPI network delays outside our control.</p>

<h2>Account Suspension</h2>
<p>We may suspend or terminate accounts that violate these terms, applicable law, or platform policies.</p>

<h2>Limitation of Liability</h2>
<p>EasyUdhar is provided on an "as is" basis. To the extent permitted by law, we are not liable for indirect or consequential damages arising from use of the service.</p>

<h2>Contact</h2>
<p>For questions about these terms, email <strong>support@easyudhar.com</strong>.</p>
"""


class Command(BaseCommand):
    help = 'Seed default privacy policy and terms of service documents.'

    def handle(self, *args, **options):
        defaults = [
            {
                'slug': LegalDocument.SLUG_PRIVACY_POLICY,
                'title': 'Privacy Policy',
                'body': PRIVACY_POLICY_BODY,
            },
            {
                'slug': LegalDocument.SLUG_TERMS_OF_SERVICE,
                'title': 'Terms of Service',
                'body': TERMS_OF_SERVICE_BODY,
            },
        ]
        effective_date = date.today()
        for item in defaults:
            doc, created = LegalDocument.objects.update_or_create(
                slug=item['slug'],
                defaults={
                    'title': item['title'],
                    'body': item['body'],
                    'version': '1.0',
                    'effective_date': effective_date,
                    'is_published': True,
                },
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action} {doc.title} ({doc.slug})'))
