from django.db import migrations, models


def backfill_chat_ids(apps, schema_editor):
    """Attribute existing Telegram alerts to a chat by matching their body.

    Alerts predate the chat_id column, so the only link back is the message text
    the alert was built from. Unmatched ones are left null — they belong to
    chats whose messages are already gone.
    """
    AdminAlert = apps.get_model('adminapp', 'AdminAlert')
    TelegramMessage = apps.get_model('adminapp', 'TelegramMessage')
    for alert in AdminAlert.objects.filter(type='telegram_message', telegram_chat_id__isnull=True):
        chat_ids = set(
            TelegramMessage.objects.filter(text=alert.body, direction='in').values_list(
                'chat_id', flat=True
            )
        )
        if len(chat_ids) == 1:
            alert.telegram_chat_id = chat_ids.pop()
            alert.save(update_fields=['telegram_chat_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0017_telegrammessage_read_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminalert',
            name='telegram_chat_id',
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_chat_ids, migrations.RunPython.noop),
    ]
