from django.conf import settings
from django.core.management.base import BaseCommand

from customerapp.email_otp import test_smtp_port


class Command(BaseCommand):
    help = 'Test Postmark SMTP on ports 587, 2525, and 25.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            required=True,
            help='Recipient email for test message (must be allowed in Postmark)',
        )

    def handle(self, *args, **options):
        host = settings.EMAIL_HOST
        user = settings.EMAIL_HOST_USER
        password = settings.EMAIL_HOST_PASSWORD
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = options['to']

        self.stdout.write(f'Host: {host}')
        self.stdout.write(f'From: {from_email}')
        self.stdout.write(f'To: {to_email}')
        self.stdout.write('')

        tests = [
            (587, True, False),
            (2525, True, False),
            (25, False, False),
        ]
        for port, use_tls, use_ssl in tests:
            result = test_smtp_port(
                host=host,
                port=port,
                username=user,
                password=password,
                use_tls=use_tls,
                use_ssl=use_ssl,
                from_email=from_email,
                to_email=to_email,
            )
            if result['sent']:
                self.stdout.write(self.style.SUCCESS(f"Port {port}: OK — email sent"))
            else:
                self.stdout.write(self.style.ERROR(f"Port {port}: FAILED — {result['error']}"))
