"""Generate EazyUdhar Admin API Postman collection."""
import json
import os

BASE = "{{base_url}}"
Q_PAGE = [("page", "1"), ("page_size", "25")]


def req(name, method, path, body=None, query=None, no_auth=False, desc=""):
    raw = f"{BASE}/{path}"
    item = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {
                "raw": raw + ("?" + "&".join(f"{k}={v}" for k, v in query) if query else ""),
                "host": ["{{base_url}}"],
                "path": [p for p in path.split("/") if p],
            },
            "description": desc,
        },
    }
    if query:
        item["request"]["url"]["query"] = [
            {"key": k, "value": v, "disabled": v == ""} for k, v in query
        ]
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2)}
    if no_auth:
        item["request"]["auth"] = {"type": "noauth"}
    return item


def folder(name, items):
    return {"name": name, "item": items}


login = req(
    "Login",
    "POST",
    "auth/login",
    {"email": "{{admin_email}}", "password": "{{admin_password}}"},
    no_auth=True,
    desc="Returns access + refresh JWT and admin user profile.",
)
login["event"] = [
    {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": [
                "if (pm.response.code === 200) {",
                "  const j = pm.response.json();",
                "  if (j.access) pm.collectionVariables.set('access_token', j.access);",
                "  if (j.refresh) pm.collectionVariables.set('refresh_token', j.refresh);",
                "}",
            ],
        },
    }
]

items = [
    folder(
        "1. Auth",
        [
            login,
            req(
                "Refresh Token",
                "POST",
                "auth/refresh",
                {"refresh": "{{refresh_token}}"},
                no_auth=True,
            ),
            req("Get Me", "GET", "auth/me", desc="Current admin profile"),
            req(
                "Logout",
                "POST",
                "auth/logout",
                {"refresh": "{{refresh_token}}"},
                desc="Invalidate refresh token. Returns 204.",
            ),
        ],
    ),
    folder(
        "2. Global Layout",
        [
            req("Global Search", "GET", "search", query=[("q", "shop")]),
            req("List Notifications", "GET", "notifications", query=Q_PAGE),
            req("Mark Notification Read", "PATCH", "notifications/{{notification_id}}", {"read": True}),
            req("Mark All Notifications Read", "POST", "notifications/mark-all-read", {}),
        ],
    ),
    folder(
        "3. Dashboard",
        [
            req("Stats (KPIs)", "GET", "dashboard/stats"),
            req("Collections Chart", "GET", "dashboard/charts/collections", query=[("range", "30d")]),
            req("Signups Chart", "GET", "dashboard/charts/signups", query=[("range", "30d")]),
            req("Outstanding by Status", "GET", "dashboard/charts/outstanding-by-status"),
            req("Recent Activity", "GET", "dashboard/activity"),
            req("Export Dashboard", "GET", "dashboard/export", query=[("format", "csv"), ("range", "30d")]),
        ],
    ),
    folder(
        "4. Sellers",
        [
            req(
                "List Sellers",
                "GET",
                "sellers",
                query=Q_PAGE + [("search", ""), ("status", ""), ("subscription_status", "")],
            ),
            req("Export Sellers CSV", "GET", "sellers/export", query=[("search", ""), ("status", "")]),
            req(
                "Invite Seller",
                "POST",
                "sellers/invite",
                {
                    "email": "newseller@example.com",
                    "business_name": "New Shop",
                    "phone": "9876543210",
                },
            ),
            req("Get Seller", "GET", "sellers/{{seller_id}}"),
            req(
                "Update Seller",
                "PATCH",
                "sellers/{{seller_id}}",
                {"business_name": "Updated Shop", "address": "123 Main St"},
            ),
            req("Seller Summary", "GET", "sellers/{{seller_id}}/summary"),
            req(
                "Reset Seller Password",
                "POST",
                "sellers/{{seller_id}}/reset-password",
                {"send_email": True},
            ),
            req(
                "Suspend Seller",
                "POST",
                "sellers/{{seller_id}}/suspend",
                {"reason": "Policy violation"},
            ),
            req(
                "Unsuspend Seller",
                "POST",
                "sellers/{{seller_id}}/unsuspend",
                {"reason": "Resolved"},
            ),
            req("Get Seller Settings", "GET", "sellers/{{seller_id}}/settings"),
            req(
                "Update Seller Settings",
                "PATCH",
                "sellers/{{seller_id}}/settings",
                {"auto_remind_enabled": True, "reminder_channels": ["sms", "whatsapp"]},
            ),
            req("Seller Customers", "GET", "sellers/{{seller_id}}/customers", query=Q_PAGE),
            req("Export Seller Customers", "GET", "sellers/{{seller_id}}/customers/export"),
            req("Seller Team", "GET", "sellers/{{seller_id}}/team", query=Q_PAGE),
            req("Seller Notifications", "GET", "sellers/{{seller_id}}/notifications", query=Q_PAGE),
            req("Seller Devices", "GET", "sellers/{{seller_id}}/devices", query=Q_PAGE),
            req("Revoke Seller Device", "DELETE", "sellers/{{seller_id}}/devices/{{device_token_id}}"),
        ],
    ),
    folder(
        "5. Customers",
        [
            req("List Customers", "GET", "customers", query=Q_PAGE + [("search", ""), ("status", "")]),
            req("Export Customers CSV", "GET", "customers/export", query=[("search", "")]),
            req("Get Customer", "GET", "customers/{{customer_id}}"),
            req(
                "Update Customer (promo)",
                "PATCH",
                "customers/{{customer_id}}",
                {"promo_code": "WELCOME10"},
            ),
            req("Reset Customer Password", "POST", "customers/{{customer_id}}/reset-password", {}),
            req(
                "Suspend Customer",
                "POST",
                "customers/{{customer_id}}/suspend",
                {"reason": "Fraud suspicion"},
            ),
            req("Unsuspend Customer", "POST", "customers/{{customer_id}}/unsuspend", {}),
            req("Customer Linked Shops", "GET", "customers/{{customer_id}}/accounts", query=Q_PAGE),
            req("Unlink Shop Account", "DELETE", "customers/{{customer_id}}/accounts/{{account_id}}"),
            req("Customer Payments", "GET", "customers/{{customer_id}}/payments", query=Q_PAGE),
            req("Customer Notifications", "GET", "customers/{{customer_id}}/notifications", query=Q_PAGE),
            req("Customer Messages", "GET", "customers/{{customer_id}}/messages", query=Q_PAGE),
            req("Customer Devices", "GET", "customers/{{customer_id}}/devices", query=Q_PAGE),
            req(
                "Revoke Customer Device",
                "DELETE",
                "customers/{{customer_id}}/devices/{{device_token_id}}",
            ),
        ],
    ),
    folder(
        "6. Team Members",
        [
            req(
                "List Team Members",
                "GET",
                "team-members",
                query=Q_PAGE + [("search", ""), ("seller_id", "")],
            ),
        ],
    ),
    folder(
        "7. Subscriptions & Billing",
        [
            req("List Plans", "GET", "subscriptions/plans"),
            req(
                "Create Plan",
                "POST",
                "subscriptions/plans",
                {
                    "name": "Enterprise",
                    "slug": "enterprise",
                    "price_monthly": 999,
                    "price_yearly": 9999,
                    "trial_days": 7,
                    "features": {"items": ["Unlimited customers"]},
                    "is_active": True,
                },
            ),
            req("Update Plan", "PATCH", "subscriptions/plans/{{plan_id}}", {"price_monthly": 499}),
            req("Deactivate Plan", "DELETE", "subscriptions/plans/{{plan_id}}"),
            req(
                "List Subscriptions",
                "GET",
                "subscriptions",
                query=Q_PAGE + [("status", ""), ("search", "")],
            ),
            req(
                "Change Subscription Plan",
                "PATCH",
                "subscriptions/{{subscription_id}}",
                {"plan_id": 2},
            ),
            req("Cancel Subscription", "POST", "subscriptions/{{subscription_id}}/cancel", {}),
            req("List Trials", "GET", "trials", query=Q_PAGE + [("expiring_in_days", "7")]),
            req("Extend Trial", "POST", "trials/{{subscription_id}}/extend", {"days": 7}),
            req(
                "Convert Trial to Paid",
                "POST",
                "trials/{{subscription_id}}/convert",
                {"plan_id": 2},
            ),
            req("Expire Trial", "POST", "trials/{{subscription_id}}/expire", {}),
            req(
                "List Payments",
                "GET",
                "payments",
                query=Q_PAGE + [("status", ""), ("seller_id", ""), ("date_from", ""), ("date_to", "")],
            ),
            req(
                "Refund Payment",
                "POST",
                "payments/{{payment_id}}/refund",
                {"amount": 100, "reason": "Duplicate charge"},
            ),
            req("List Invoices", "GET", "subscriptions/invoices", query=Q_PAGE),
            req("Download Invoice", "GET", "subscriptions/invoices/{{invoice_id}}/download"),
        ],
    ),
    folder(
        "8. Transactions",
        [
            req(
                "List Transactions",
                "GET",
                "transactions",
                query=Q_PAGE
                + [
                    ("type", ""),
                    ("seller_id", ""),
                    ("customer_id", ""),
                    ("date_from", ""),
                    ("date_to", ""),
                    ("search", ""),
                ],
            ),
            req("List Sync Queue", "GET", "transactions/sync-queue", query=Q_PAGE),
            req("Retry Sync Item", "POST", "transactions/sync-queue/{{sync_queue_id}}/retry", {}),
            req("Dismiss Sync Item", "POST", "transactions/sync-queue/{{sync_queue_id}}/dismiss", {}),
        ],
    ),
    folder(
        "9. Communications",
        [
            req(
                "Reminder Logs (all)",
                "GET",
                "reminder-logs",
                query=Q_PAGE
                + [
                    ("channel", ""),
                    ("type", ""),
                    ("status", ""),
                    ("seller_id", ""),
                    ("date_from", ""),
                    ("date_to", ""),
                ],
            ),
            req("Reminder Logs (SMS)", "GET", "reminder-logs", query=Q_PAGE + [("channel", "sms")]),
            req(
                "Reminder Logs (WhatsApp)",
                "GET",
                "reminder-logs",
                query=Q_PAGE + [("channel", "whatsapp")],
            ),
            req("Reminder Logs (Push)", "GET", "reminder-logs", query=Q_PAGE + [("channel", "push")]),
            req("Resend Failed Reminder", "POST", "reminder-logs/{{reminder_log_id}}/resend", {}),
            req(
                "OTP Records",
                "GET",
                "otp-records",
                query=Q_PAGE + [("phone", ""), ("purpose", ""), ("date_from", ""), ("date_to", "")],
            ),
        ],
    ),
    folder(
        "10. Promo & Growth",
        [
            req("List Promo Codes", "GET", "promo-codes", query=Q_PAGE),
            req(
                "Create Promo Code",
                "POST",
                "promo-codes",
                {
                    "code": "SAVE20",
                    "discount_type": "percent",
                    "discount_value": 20,
                    "max_uses": 100,
                    "is_active": True,
                },
            ),
            req("Update Promo Code", "PATCH", "promo-codes/{{promo_id}}", {"discount_value": 25}),
            req("Deactivate Promo Code", "DELETE", "promo-codes/{{promo_id}}"),
            req(
                "List Promo Redemptions",
                "GET",
                "promo-redemptions",
                query=Q_PAGE + [("promo_code", ""), ("customer_id", ""), ("date_from", ""), ("date_to", "")],
            ),
        ],
    ),
    folder(
        "11. Shops & Accounts",
        [
            req(
                "List Seller Customers (global)",
                "GET",
                "seller-customers",
                query=Q_PAGE + [("search", ""), ("seller_id", ""), ("status", "")],
            ),
            req(
                "List Customer Accounts (global)",
                "GET",
                "customer-accounts",
                query=Q_PAGE + [("search", ""), ("seller_id", ""), ("customer_id", "")],
            ),
        ],
    ),
    folder(
        "12. Support & Moderation",
        [
            req(
                "List Suspensions",
                "GET",
                "suspensions",
                query=Q_PAGE + [("status", "active"), ("account_type", "")],
            ),
            req(
                "List Chat Messages",
                "GET",
                "messages",
                query=Q_PAGE + [("seller_id", ""), ("customer_id", ""), ("flagged", "")],
            ),
            req("Flag Message", "POST", "messages/{{message_id}}/flag", {}),
            req("Delete Message", "DELETE", "messages/{{message_id}}"),
            req(
                "List Tickets",
                "GET",
                "tickets",
                query=Q_PAGE + [("status", ""), ("priority", ""), ("assigned_to", "")],
            ),
            req(
                "Update Ticket",
                "PATCH",
                "tickets/{{ticket_id}}",
                {"status": "in_progress", "assigned_to_admin_id": 1},
            ),
            req(
                "Reply to Ticket",
                "POST",
                "tickets/{{ticket_id}}/replies",
                {"body": "We are looking into this."},
            ),
        ],
    ),
    folder(
        "13. Reports",
        [
            req(
                "Collections Report",
                "GET",
                "reports/collections",
                query=[("group_by", "day"), ("date_from", ""), ("date_to", ""), ("seller_id", "")],
            ),
            req(
                "Overdue Report",
                "GET",
                "reports/overdue",
                query=Q_PAGE + [("group_by", "seller"), ("min_amount", "")],
            ),
            req(
                "Daily Summary Logs",
                "GET",
                "reports/daily-summary",
                query=Q_PAGE + [("seller_id", ""), ("date_from", ""), ("date_to", "")],
            ),
            req(
                "Export Report",
                "GET",
                "reports/export",
                query=[("format", "csv"), ("report", "collections"), ("date_from", ""), ("date_to", "")],
            ),
        ],
    ),
    folder(
        "14. System",
        [
            req("List Admin Users", "GET", "system/admins", query=Q_PAGE),
            req(
                "Create Admin User",
                "POST",
                "system/admins",
                {
                    "email": "support@eazyudhar.com",
                    "name": "Support Agent",
                    "role": "support",
                    "password": "ChangeMe@2026",
                },
            ),
            req(
                "Update Admin User",
                "PATCH",
                "system/admins/{{admin_user_id}}",
                {"role": "finance", "is_active": True},
            ),
            req("Deactivate Admin User", "DELETE", "system/admins/{{admin_user_id}}"),
            req(
                "Reset Admin Password",
                "POST",
                "system/admins/{{admin_user_id}}/reset-password",
                {"password": "NewPass@2026"},
            ),
            req("List Cron Jobs", "GET", "system/cron"),
            req("Trigger Cron Job", "POST", "system/cron/run_auto_reminders/trigger", {}),
            req("System Health", "GET", "system/health"),
            req(
                "Audit Log",
                "GET",
                "audit-log",
                query=Q_PAGE + [("action", ""), ("actor_id", ""), ("date_from", ""), ("date_to", "")],
            ),
        ],
    ),
]


def count_requests(folder_items):
    total = 0
    for item in folder_items:
        if "item" in item:
            total += count_requests(item["item"])
        else:
            total += 1
    return total


collection = {
    "info": {
        "_postman_id": "eazyudhar-admin-api-v1",
        "name": "EazyUdhar Admin API v1",
        "description": (
            "Complete Postman collection for EazyUdhar Admin Panel APIs.\n\n"
            "**Setup**\n"
            "1. Set `base_url` (e.g. `http://192.168.0.145:8099/admin-api/v1`)\n"
            "2. Run **1. Auth > Login** — tokens are saved automatically\n"
            "3. All other requests use Bearer `access_token`\n\n"
            "**Seed admin:** `admin@eazyudhar.com` / `Admin@2026`\n\n"
            "See `API_REQUIREMENTS.md` for full request/response shapes."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
    },
    "variable": [
        {"key": "base_url", "value": "http://192.168.0.145:8099/admin-api/v1"},
        {"key": "admin_email", "value": "admin@eazyudhar.com"},
        {"key": "admin_password", "value": "Admin@2026"},
        {"key": "access_token", "value": ""},
        {"key": "refresh_token", "value": ""},
        {"key": "seller_id", "value": "1"},
        {"key": "customer_id", "value": "1"},
        {"key": "subscription_id", "value": "1"},
        {"key": "plan_id", "value": "1"},
        {"key": "payment_id", "value": "1"},
        {"key": "ticket_id", "value": "1"},
        {"key": "promo_id", "value": "1"},
        {"key": "admin_user_id", "value": "1"},
        {"key": "notification_id", "value": "1"},
        {"key": "sync_queue_id", "value": "1"},
        {"key": "reminder_log_id", "value": ""},
        {"key": "message_id", "value": ""},
        {"key": "device_token_id", "value": ""},
        {"key": "account_id", "value": ""},
        {"key": "invoice_id", "value": "1"},
    ],
    "item": items,
}

out_path = os.path.join(os.path.dirname(__file__), "EazyUdhar_Admin_API.postman_collection.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=2, ensure_ascii=False)

print(f"Written {out_path} with {count_requests(items)} requests")
