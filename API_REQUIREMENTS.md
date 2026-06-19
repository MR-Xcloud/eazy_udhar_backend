# EazyUdhar Admin Panel — Complete API Requirements

This document lists **every API endpoint** required to make the EazyUdhar admin panel fully functional — every page, tab, filter, button, dropdown action, and global UI control.

---

## Table of Contents

1. [API Conventions](#1-api-conventions)
2. [Authentication & Session](#2-authentication--session)
3. [Global Layout (Top Bar & Sidebar)](#3-global-layout-top-bar--sidebar)
4. [Dashboard](#4-dashboard)
5. [Users — Sellers](#5-users--sellers)
6. [Users — Customers](#6-users--customers)
7. [Users — Team Members](#7-users--team-members)
8. [Subscriptions & Billing](#8-subscriptions--billing)
9. [Ledger & Transactions](#9-ledger--transactions)
10. [Communications](#10-communications)
11. [Promo & Growth](#11-promo--growth)
12. [Shops & Accounts](#12-shops--accounts)
13. [Support & Moderation](#13-support--moderation)
14. [Reports](#14-reports)
15. [System](#15-system)
16. [Shared Data Models](#16-shared-data-models)
17. [Master Endpoint Index](#17-master-endpoint-index)
18. [Implementation Status](#18-implementation-status)

---

## 1. API Conventions

| Item | Value |
|------|-------|
| **Base URL** | `{VITE_ADMIN_API_BASE}` — default `http://192.168.0.146/admin-api/v1` |
| **Auth** | JWT Bearer token in `Authorization: Bearer <access_token>` |
| **Content-Type** | `application/json` for request/response bodies |
| **Pagination** | Query: `page` (1-based), `page_size`. Response wrapper below. |
| **Search** | Query param `search` (free-text) on list endpoints |
| **Errors** | HTTP 4xx/5xx with JSON body `{ "detail": "Human-readable message" }` |
| **Token storage** | Client stores `access` + `refresh` in `localStorage` |

### Paginated list response

```json
{
  "data": [ /* array of items */ ],
  "meta": {
    "page": 1,
    "page_size": 25,
    "total": 1284
  }
}
```

### Admin roles

`super_admin` | `support` | `finance` | `read_only`

---

## 2. Authentication & Session

**Admin route:** `/login`  
**Used by:** Login form, `AuthProvider`, admin layout guard, top-bar sign out.

| # | Method | Endpoint | Triggered by | Request | Response | Notes |
|---|--------|----------|--------------|---------|----------|-------|
| 2.1 | `POST` | `/auth/login` | **Sign in** button on login page | `{ "email": string, "password": string }` | `{ "access": string, "refresh": string, "user"?: AdminUser }` | `auth: false` — no token required |
| 2.2 | `GET` | `/auth/me` | App load, post-login session restore | — | `AdminUser` | Returns current admin profile; 401 if invalid token |
| 2.3 | `POST` | `/auth/refresh` | Automatic on 401 (client internal) | `{ "refresh": string }` | `{ "access": string, "refresh"?: string }` | Rotates access token |
| 2.4 | `POST` | `/auth/logout` | **Sign out** in top-bar user menu | — (optional `{ "refresh": string }`) | `204` or `{ "detail": "ok" }` | Invalidate refresh token server-side |

### `AdminUser` shape

```ts
{
  id: number | string;
  email: string;
  name?: string;
  role?: "super_admin" | "support" | "finance" | "read_only";
  avatar_url?: string | null;
}
```

---

## 3. Global Layout (Top Bar & Sidebar)

**Components:** `top-bar.tsx`, `app-sidebar.tsx`, `_admin.tsx` layout.

Sidebar navigation is route-only (no API). Top bar controls that need backend:

| # | Method | Endpoint | UI element | Purpose |
|---|--------|----------|------------|---------|
| 3.1 | `GET` | `/search` | **Global search** input (top bar) | Unified search across sellers, customers, phone numbers. Query: `?q=` |
| 3.2 | `GET` | `/notifications` or `/admin/alerts` | **Bell** icon (top bar) | Unread admin alerts (failed deliveries, suspensions, trial expiries). Returns count + list |
| 3.3 | `POST` | `/auth/logout` | **Sign out** dropdown item | See §2.4 |
| 3.4 | `GET` | `/auth/me` | Avatar / name / role display | See §2.2 |

### `GET /search` suggested response

```json
{
  "sellers": [{ "id": 1, "business_name": "...", "phone": "..." }],
  "customers": [{ "id": 1, "full_name": "...", "phone": "..." }],
  "seller_customers": [{ "id": 1, "name": "...", "phone": "...", "seller_id": 1 }]
}
```

### `GET /notifications` suggested response

```json
{
  "unread_count": 3,
  "data": [
    {
      "id": 1,
      "type": "sms_failed" | "trial_expiring" | "suspension" | "sync_error",
      "title": string,
      "body": string,
      "link": string,
      "created_at": "ISO8601",
      "read": boolean
    }
  ]
}
```

**Additional implied actions on notifications panel (when wired):**

| Method | Endpoint | Action |
|--------|----------|--------|
| `PATCH` | `/notifications/{id}` | Mark single notification read |
| `POST` | `/notifications/mark-all-read` | Mark all read |

---

## 4. Dashboard

**Admin route:** `/`  
**File:** `_admin.index.tsx`

### 4.1 Data endpoints (wired in frontend)

| # | Method | Endpoint | UI section | Query params | Response |
|---|--------|----------|------------|--------------|----------|
| 4.1 | `GET` | `/dashboard/stats` | 8 KPI cards | — | `Stats` (see below) |
| 4.2 | `GET` | `/dashboard/charts/collections` | Collections trend area chart | `range=7d\|30d\|90d` | `{ "data": [{ "date": string, "collections": number, "credits": number }] }` |
| 4.3 | `GET` | `/dashboard/charts/signups` | New signups bar chart | `range=7d\|30d` | `{ "data": [{ "date": string, "sellers": number, "customers": number }] }` |

### `Stats` response shape

```ts
{
  sellers_total: number;
  sellers_active: number;
  sellers_suspended: number;
  customers_total: number;
  customers_active: number;
  customers_suspended: number;
  outstanding_total: number;        // paise or rupees — be consistent
  collections_today: number;
  collections_change_pct?: number;
  overdue_customers: number;
  overdue_amount: number;
  trials_active: number;
  subscriptions_active: number;
  mrr?: number;
  arr?: number;
  sms_sent_today: number;
  reminders_sent_today: number;
  sms_failed_today: number;
  push_failed_today: number;
}
```

### 4.2 Additional endpoints for full dashboard

| # | Method | Endpoint | UI section | Notes |
|---|--------|----------|------------|-------|
| 4.4 | `GET` | `/dashboard/charts/outstanding-by-status` | **Outstanding by status** pie chart | `{ "data": [{ "name": "Pending"\|"Overdue"\|"Settled", "value": number }] }` |
| 4.5 | `GET` | `/dashboard/activity` | **Recent activity** list | `{ "data": [{ "type": string, "title": string, "who": string, "time": string, "tone": string }] }` |

### 4.3 Button actions

| Button | Method | Endpoint | Request |
|--------|--------|----------|---------|
| **Last 30 days** (date range) | `GET` | `/dashboard/charts/collections` + `/dashboard/charts/signups` | `?range=7d\|30d\|90d` |
| **Export report** | `GET` | `/reports/export` or `/dashboard/export` | `?format=csv\|xlsx&range=30d` — returns file download |

---

## 5. Users — Sellers

### 5.1 Sellers list

**Admin route:** `/sellers`  
**File:** `_admin.sellers.tsx`

| # | Method | Endpoint | Triggered by | Query params | Response |
|---|--------|----------|--------------|--------------|----------|
| 5.1 | `GET` | `/sellers` | Page load, search, filters, pagination | `page`, `page_size`, `search`, `status` (`active`\|`suspended`), `subscription_status` (`trial`\|`active`\|`expired`) | `Paginated<Seller>` |

#### Filters (UI)

| Control | Query param | Status in UI |
|---------|-------------|--------------|
| Search input | `search` | Wired (local state → API) |
| Status dropdown | `status` | **Needs wiring** — UI exists, handler empty |
| Subscription dropdown | `subscription_status` | **Needs wiring** — UI exists, no param sent |

#### Header buttons

| Button | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| **Export CSV** | `GET` | `/sellers/export` | `?search=&status=&subscription_status=` — CSV file |
| **Invite seller** | `POST` | `/sellers/invite` | `{ "email": string, "business_name"?: string, "phone"?: string }` |

#### Row actions (⋯ dropdown per seller)

| Menu item | Method | Endpoint | Request body |
|-----------|--------|----------|--------------|
| **View details** | — | Navigate to `/sellers/{id}` | — |
| **Reset password** | `POST` | `/sellers/{id}/reset-password` | `{ "send_email": true }` optional |
| **Export customers** | `GET` | `/sellers/{id}/customers/export` | CSV download |
| **Suspend** | `POST` | `/sellers/{id}/suspend` | `{ "reason": string }` |
| **Unsuspend** | `POST` | `/sellers/{id}/unsuspend` | `{ "reason"?: string }` |

*Alternative:* `PATCH /sellers/{id}` with `{ "status": "active" | "suspended" }`

#### Pagination

| Button | Method | Endpoint |
|--------|--------|----------|
| **Previous** | `GET` | `/sellers?page={page-1}&...` |
| **Next** | `GET` | `/sellers?page={page+1}&...` |

#### `Seller` list item shape

```ts
{
  id: number;
  business_name: string;
  full_name: string;
  email: string;
  phone: string;
  gst_number?: string | null;
  customers_count?: number;
  outstanding_total?: number;
  status?: "active" | "suspended";
  subscription_status?: "trial" | "active" | "expired" | null;
  created_at: string;       // ISO8601
  last_login_at?: string | null;
}
```

---

### 5.2 Seller detail

**Admin route:** `/sellers/$id`  
**File:** `_admin.sellers.$id.tsx`

#### Header summary card (currently static demo — needs API)

| # | Method | Endpoint | UI element |
|---|--------|----------|------------|
| 5.2 | `GET` | `/sellers/{id}/summary` | Header card: name, status, subscription, contact, outstanding, customer count, overdue count |

*Can be part of `GET /sellers/{id}` response instead of a separate endpoint.*

#### Header buttons

| Button | Method | Endpoint |
|--------|--------|----------|
| **Reset password** | `POST` | `/sellers/{id}/reset-password` |
| **Suspend** | `POST` | `/sellers/{id}/suspend` |

#### Tabs

| Tab | Method | Endpoint | Response / purpose |
|-----|--------|----------|-------------------|
| **Profile** | `GET` | `/sellers/{id}` | Full seller profile (business, address, GST, bank, KYC, etc.) |
| **Settings** | `GET` | `/sellers/{id}/settings` | `SellerSettings` — reminder channels, auto-remind, daily summary, push |
| **Settings** (save) | `PATCH` | `/sellers/{id}/settings` | Update seller notification/reminder preferences |
| **Customers** | `GET` | `/sellers/{id}/customers` | `Paginated<SellerCustomer>` — ledger contacts for this seller |
| **Transactions** | `GET` | `/transactions?seller_id={id}` | `Paginated<LedgerTransaction>` |
| **Team** | `GET` | `/sellers/{id}/team` | `Paginated<TeamMember>` |
| **Notifications** | `GET` | `/sellers/{id}/notifications` | `Paginated<SellerNotification>` |
| **Devices** | `GET` | `/sellers/{id}/devices` | `Paginated<SellerDeviceToken>` |

#### Implied tab-level actions (when UI is built out)

| Action | Method | Endpoint |
|--------|--------|----------|
| Remove team member | `DELETE` | `/sellers/{id}/team/{member_id}` |
| Revoke device token | `DELETE` | `/sellers/{id}/devices/{token_id}` |
| Resend notification | `POST` | `/sellers/{id}/notifications/{id}/resend` |

---

## 6. Users — Customers

### 6.1 Customers list

**Admin route:** `/customers`  
**File:** `_admin.customers.tsx`

| # | Method | Endpoint | Query params | Response |
|---|--------|----------|--------------|----------|
| 6.1 | `GET` | `/customers` | `page`, `page_size`, `search`, `status` | `Paginated<Customer>` |

#### Header button

| Button | Method | Endpoint |
|--------|--------|----------|
| **Export CSV** | `GET` | `/customers/export` | `?search=&status=` |

#### Row actions (⋯ dropdown)

| Menu item | Method | Endpoint | Request |
|-----------|--------|----------|---------|
| **View details** | — | Navigate `/customers/{id}` | — |
| **Edit promo code** | `PATCH` | `/customers/{id}` | `{ "promo_code": string \| null }` |
| **Suspend** | `POST` | `/customers/{id}/suspend` | `{ "reason": string }` |
| **Unsuspend** | `POST` | `/customers/{id}/unsuspend` | — |

#### Pagination

| Button | Method | Endpoint |
|--------|--------|----------|
| **Previous** / **Next** | `GET` | `/customers?page=N&...` |

#### `Customer` list item shape

```ts
{
  id: number;
  full_name: string;
  email?: string | null;
  phone: string;
  promo_code?: string | null;
  linked_shops?: number;
  status?: "active" | "suspended";
  created_at: string;
}
```

---

### 6.2 Customer detail

**Admin route:** `/customers/$id`  
**File:** `_admin.customers.$id.tsx`

#### Header buttons

| Button | Method | Endpoint |
|--------|--------|----------|
| **Reset password** | `POST` | `/customers/{id}/reset-password` |
| **Suspend** | `POST` | `/customers/{id}/suspend` |

#### Tabs

| Tab | Method | Endpoint | Response |
|-----|--------|----------|----------|
| **Profile** | `GET` | `/customers/{id}` | Full customer profile |
| **Linked shops** | `GET` | `/customers/{id}/accounts` | `Paginated<CustomerAccount>` |
| **Payments** | `GET` | `/customers/{id}/payments` | `Paginated<CustomerPayment>` |
| **Notifications** | `GET` | `/customers/{id}/notifications` | Notification history |
| **Chat threads** | `GET` | `/customers/{id}/messages` | `Paginated<ShopMessage>` threads |
| **Devices** | `GET` | `/customers/{id}/devices` | `Paginated<CustomerDeviceToken>` |

#### Implied tab actions

| Action | Method | Endpoint |
|--------|--------|----------|
| Revoke device | `DELETE` | `/customers/{id}/devices/{token_id}` |
| Unlink shop account | `DELETE` | `/customers/{id}/accounts/{account_id}` |

---

## 7. Users — Team Members

**Admin route:** `/team-members`  
**File:** `_admin.team-members.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 7.1 | `GET` | `/team-members` | Aggregate all `TeamMember` rows across sellers. Query: `page`, `page_size`, `search`, `seller_id` |

#### Implied actions (when list UI is built)

| Action | Method | Endpoint |
|--------|--------|----------|
| View seller | — | Navigate `/sellers/{seller_id}` | |
| Deactivate member | `PATCH` | `/sellers/{seller_id}/team/{id}` | `{ "status": "inactive" }` |

---

## 8. Subscriptions & Billing

### 8.1 Active Subscriptions

**Route:** `/subscriptions` | **File:** `_admin.subscriptions.index.tsx`

| # | Method | Endpoint | Query | Response |
|---|--------|----------|-------|----------|
| 8.1 | `GET` | `/subscriptions` | `page`, `page_size`, `status` (`trial`\|`active`\|`cancelled`), `search` | `Paginated<Subscription>` |

```ts
// Subscription
{
  id: number;
  seller_id: number;
  seller_name: string;
  plan_id: number;
  plan_name: string;
  status: "trial" | "active" | "cancelled" | "expired";
  billing_amount: number;
  currency: "INR";
  current_period_start: string;
  current_period_end: string;
  trial_ends_at?: string | null;
  razorpay_subscription_id?: string | null;
}
```

**Implied actions:** cancel subscription, change plan, view seller.

| Action | Method | Endpoint |
|--------|--------|----------|
| Cancel | `POST` | `/subscriptions/{id}/cancel` |
| Change plan | `PATCH` | `/subscriptions/{id}` | `{ "plan_id": number }` |

---

### 8.2 Plans & Pricing

**Route:** `/subscriptions/plans` | **File:** `_admin.subscriptions.plans.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 8.2 | `GET` | `/subscriptions/plans` | List plans (Free Trial, Basic, Pro) |
| 8.3 | `POST` | `/subscriptions/plans` | **Create plan** button (future UI) |
| 8.4 | `PATCH` | `/subscriptions/plans/{id}` | **Edit plan** (future UI) |
| 8.5 | `DELETE` | `/subscriptions/plans/{id}` | Deactivate plan |

```ts
// Plan
{
  id: number;
  name: string;           // "Free Trial", "Basic", "Pro"
  slug: string;
  price_monthly: number;
  price_yearly?: number;
  trial_days: number;
  features: string[];
  is_active: boolean;
  sort_order: number;
}
```

---

### 8.3 Trial Management

**Route:** `/subscriptions/trials` | **File:** `_admin.subscriptions.trials.tsx`

| # | Method | Endpoint | Query | Purpose |
|---|--------|----------|-------|---------|
| 8.6 | `GET` | `/trials` | `expiring_in_days=7`, `page`, `page_size` | Sellers on trial |

| Action (per row) | Method | Endpoint | Body |
|------------------|--------|----------|------|
| **Extend trial** | `POST` | `/trials/{id}/extend` | `{ "days": number }` |
| **Convert to paid** | `POST` | `/trials/{id}/convert` | `{ "plan_id": number }` |
| **Expire trial** | `POST` | `/trials/{id}/expire` | — |

---

### 8.4 Razorpay Payments

**Route:** `/subscriptions/payments` | **File:** `_admin.subscriptions.payments.tsx`

| # | Method | Endpoint | Query | Purpose |
|---|--------|----------|-------|---------|
| 8.7 | `GET` | `/payments` | `page`, `page_size`, `status`, `seller_id`, `date_from`, `date_to` | Razorpay payment records |

```ts
{
  id: number;
  seller_id: number;
  order_id: string;
  payment_id: string;
  amount: number;
  currency: "INR";
  status: "created" | "authorized" | "captured" | "failed" | "refunded";
  method?: string;
  created_at: string;
  refunded_at?: string | null;
}
```

| Action | Method | Endpoint |
|--------|--------|----------|
| **Issue refund** | `POST` | `/payments/{id}/refund` | `{ "amount"?: number, "reason": string }` |

---

### 8.5 Invoices & Receipts

**Route:** `/subscriptions/invoices` | **File:** `_admin.subscriptions.invoices.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 8.8 | `GET` | `/subscriptions/invoices` | List invoices per billing cycle |
| 8.9 | `GET` | `/subscriptions/invoices/{id}/download` | PDF download |

```ts
{
  id: number;
  subscription_id: number;
  seller_id: number;
  invoice_number: string;
  amount: number;
  tax_amount?: number;
  status: "draft" | "paid" | "void";
  period_start: string;
  period_end: string;
  pdf_url?: string;
  created_at: string;
}
```

---

## 9. Ledger & Transactions

### 9.1 All Transactions

**Route:** `/transactions` | **File:** `_admin.transactions.index.tsx`

| # | Method | Endpoint | Query | Purpose |
|---|--------|----------|-------|---------|
| 9.1 | `GET` | `/transactions` | `page`, `page_size`, `type` (`ledger`\|`payment`\|`razorpay`), `seller_id`, `customer_id`, `date_from`, `date_to`, `search` | Unified transaction feed |

---

### 9.2 Seller Ledger

**Route:** `/transactions/ledger` | **File:** `_admin.transactions.ledger.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 9.2 | `GET` | `/transactions` | `type=ledger` (+ filters above) |

```ts
// LedgerTransaction
{
  id: number;
  seller_id: number;
  seller_customer_id?: number;
  customer_name?: string;
  type: "credit_added" | "payment_received" | "advance_deposit" | "advance_use";
  amount: number;
  balance_after?: number;
  note?: string;
  created_by?: string;
  created_at: string;
  source: "app" | "offline_sync" | "admin";
}
```

---

### 9.3 Customer Payments

**Route:** `/transactions/payments` | **File:** `_admin.transactions.payments.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 9.3 | `GET` | `/transactions` | `type=payment` |

```ts
// CustomerPayment
{
  id: number;
  customer_id: number;
  seller_id: number;
  seller_customer_id: number;
  amount: number;
  method: "cash" | "upi" | "bank" | "other";
  status: "pending" | "success" | "failed";
  reference?: string;
  created_at: string;
}
```

---

### 9.4 Offline Sync Queue

**Route:** `/transactions/sync` | **File:** `_admin.transactions.sync.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 9.4 | `GET` | `/transactions/sync-queue` | Per-seller pending offline ops + duplicate detection |

```ts
{
  id: number;
  seller_id: number;
  seller_name: string;
  operation_type: string;
  payload_summary: string;
  status: "pending" | "processing" | "failed" | "duplicate";
  error_message?: string;
  created_at: string;
  retry_count: number;
}
```

| Action | Method | Endpoint |
|--------|--------|----------|
| **Retry sync item** | `POST` | `/transactions/sync-queue/{id}/retry` |
| **Dismiss duplicate** | `POST` | `/transactions/sync-queue/{id}/dismiss` |

---

## 10. Communications

### 10.1 SMS Logs (Nimbus)

**Route:** `/comms/sms` | **File:** `_admin.comms.sms.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 10.1 | `GET` | `/reminder-logs` | `channel=sms`, `page`, `page_size`, `status`, `date_from`, `date_to`, `seller_id` |

---

### 10.2 WhatsApp Logs

**Route:** `/comms/whatsapp` | **File:** `_admin.comms.whatsapp.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 10.2 | `GET` | `/reminder-logs` | `channel=whatsapp`, (+ filters) |

---

### 10.3 Push Notifications

**Route:** `/comms/push` | **File:** `_admin.comms.push.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 10.3 | `GET` | `/reminder-logs` | `channel=push`, (+ filters) |

---

### 10.4 Reminder Logs (all channels)

**Route:** `/comms/reminders` | **File:** `_admin.comms.reminders.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 10.4 | `GET` | `/reminder-logs` | `page`, `page_size`, `channel`, `type` (`manual`\|`auto`), `status`, `seller_id` |

```ts
// ReminderLog
{
  id: number;
  seller_id?: number;
  customer_id?: number;
  channel: "sms" | "whatsapp" | "push";
  type: "manual" | "auto";
  template_name?: string;
  recipient: string;          // phone or device id (masked)
  status: "sent" | "delivered" | "failed";
  error_message?: string;
  provider_message_id?: string;
  created_at: string;
}
```

| Action | Method | Endpoint |
|--------|--------|----------|
| **Resend failed** | `POST` | `/reminder-logs/{id}/resend` |

---

### 10.5 OTP Records

**Route:** `/comms/otp` | **File:** `_admin.comms.otp.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 10.5 | `GET` | `/otp-records` | `page`, `page_size`, `phone`, `purpose`, `date_from`, `date_to` |

```ts
{
  id: number;
  phone: string;              // masked e.g. +91 98••• ••342
  purpose: "login" | "verify" | "reset_password";
  status: "sent" | "verified" | "expired" | "failed";
  attempts: number;
  ip_address?: string;
  created_at: string;
  verified_at?: string | null;
}
```

---

## 11. Promo & Growth

### 11.1 Promo Codes

**Route:** `/promos` | **File:** `_admin.promos.index.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 11.1 | `GET` | `/promo-codes` | List promo codes |
| 11.2 | `POST` | `/promo-codes` | Create promo |
| 11.3 | `PATCH` | `/promo-codes/{id}` | Edit promo |
| 11.4 | `DELETE` | `/promo-codes/{id}` | Deactivate promo |

```ts
{
  id: number;
  code: string;
  discount_type: "percent" | "flat";
  discount_value: number;
  max_uses?: number | null;
  uses_count: number;
  valid_from: string;
  valid_until: string;
  is_active: boolean;
  created_at: string;
}
```

---

### 11.2 Promo Redemptions

**Route:** `/promos/redemptions` | **File:** `_admin.promos.redemptions.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 11.5 | `GET` | `/promo-redemptions` | `page`, `page_size`, `promo_code`, `customer_id`, `date_from`, `date_to` |

```ts
{
  id: number;
  promo_code: string;
  customer_id: number;
  customer_name: string;
  seller_id?: number;
  redeemed_at: string;
}
```

---

## 12. Shops & Accounts

### 12.1 Seller Businesses

**Route:** `/shops/businesses` | **File:** `_admin.shops.businesses.tsx`

| # | Method | Endpoint | Notes |
|---|--------|----------|-------|
| 12.1 | `GET` | `/sellers` | Business-focused view: `?view=business` or dedicated fields in seller list |

Extended fields: `address`, `city`, `state`, `pincode`, `gst_number`, `business_type`.

| Action | Method | Endpoint |
|--------|--------|----------|
| **Edit business** | `PATCH` | `/sellers/{id}` | `{ "business_name", "address", "gst_number", ... }` |

---

### 12.2 Seller Customers (Ledger Contacts)

**Route:** `/shops/seller-customers` | **File:** `_admin.shops.seller-customers.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 12.2 | `GET` | `/seller-customers` | `page`, `page_size`, `search` (phone dedupe), `seller_id`, `status` |

```ts
// SellerCustomer
{
  id: number;
  seller_id: number;
  seller_name: string;
  name: string;
  phone: string;
  outstanding: number;
  status: "active" | "overdue" | "settled";
  last_transaction_at?: string;
  created_at: string;
}
```

---

### 12.3 Customer Shop Accounts

**Route:** `/shops/customer-accounts` | **File:** `_admin.shops.customer-accounts.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 12.3 | `GET` | `/customer-accounts` | `page`, `page_size`, `search`, `seller_id`, `customer_id` |

```ts
// CustomerAccount
{
  id: number;
  customer_id: number;
  customer_name: string;
  seller_id: number;
  seller_name: string;
  outstanding: number;
  credit_limit?: number;
  status: "active" | "overdue" | "suspended";
  linked_at: string;
}
```

---

## 13. Support & Moderation

### 13.1 Account Suspensions

**Route:** `/moderation/suspensions` | **File:** `_admin.moderation.suspensions.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 13.1 | `GET` | `/suspensions` | `page`, `page_size`, `status` (`active`\|`historical`), `account_type` (`seller`\|`customer`) |

```ts
{
  id: number;
  account_type: "seller" | "customer";
  account_id: number;
  account_name: string;
  reason: string;
  suspended_by_admin_id: number;
  suspended_by_admin_email: string;
  suspended_at: string;
  lifted_at?: string | null;
  is_active: boolean;
}
```

---

### 13.2 Chat Moderation

**Route:** `/moderation/chat` | **File:** `_admin.moderation.chat.tsx`  
**Phase 2** — read-only with flag/delete.

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 13.2 | `GET` | `/messages` | `page`, `page_size`, `seller_id`, `customer_id`, `flagged` |

```ts
// ShopMessage
{
  id: number;
  seller_id: number;
  customer_id: number;
  sender_type: "seller" | "customer";
  body: string;
  flagged: boolean;
  created_at: string;
}
```

| Action | Method | Endpoint |
|--------|--------|----------|
| **Flag message** | `POST` | `/messages/{id}/flag` |
| **Delete message** | `DELETE` | `/messages/{id}` |

---

### 13.3 Help Tickets

**Route:** `/moderation/tickets` | **File:** `_admin.moderation.tickets.tsx`  
**Phase 2**

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 13.3 | `GET` | `/tickets` | `page`, `page_size`, `status`, `priority`, `assigned_to` |

```ts
{
  id: number;
  subject: string;
  description: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high";
  requester_type: "seller" | "customer";
  requester_id: number;
  assigned_to_admin_id?: number;
  created_at: string;
  updated_at: string;
}
```

| Action | Method | Endpoint |
|--------|--------|----------|
| **Assign ticket** | `PATCH` | `/tickets/{id}` | `{ "assigned_to_admin_id": number }` |
| **Update status** | `PATCH` | `/tickets/{id}` | `{ "status": string }` |
| **Reply** | `POST` | `/tickets/{id}/replies` | `{ "body": string }` |

---

## 14. Reports

### 14.1 Collections Report

**Route:** `/reports/collections` | **File:** `_admin.reports.collections.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 14.1 | `GET` | `/reports/collections` | `group_by=day\|week\|month`, `date_from`, `date_to`, `seller_id` |

**Implied:** `GET /reports/collections/export?format=csv`

---

### 14.2 Overdue Report

**Route:** `/reports/overdue` | **File:** `_admin.reports.overdue.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 14.2 | `GET` | `/reports/overdue` | `group_by=seller`, `page`, `page_size`, `min_amount` |

---

### 14.3 Daily Summary Logs

**Route:** `/reports/daily` | **File:** `_admin.reports.daily.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 14.3 | `GET` | `/reports/daily-summary` | `page`, `page_size`, `seller_id`, `date_from`, `date_to` |

Returns `SellerNotification` where `type = daily_summary` with delivery status.

---

## 15. System

### 15.1 Admin Users & Roles

**Route:** `/system/admins` | **File:** `_admin.system.admins.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 15.1 | `GET` | `/system/admins` | List admin accounts |
| 15.2 | `POST` | `/system/admins` | Invite / create admin |
| 15.3 | `PATCH` | `/system/admins/{id}` | Update role, name, status |
| 15.4 | `DELETE` | `/system/admins/{id}` | Deactivate admin |
| 15.5 | `POST` | `/system/admins/{id}/reset-password` | Force password reset |

```ts
{
  id: number;
  email: string;
  name?: string;
  role: "super_admin" | "support" | "finance" | "read_only";
  is_active: boolean;
  last_login_at?: string;
  created_at: string;
}
```

---

### 15.2 Cron Jobs

**Route:** `/system/cron` | **File:** `_admin.system.cron.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 15.6 | `GET` | `/system/cron` | List scheduled jobs with last run status |
| 15.7 | `POST` | `/system/cron/{job}/trigger` | Manual trigger |

Known jobs: `run_auto_reminders`, `send_daily_summary`, `send_nightly_sms`

```ts
{
  name: string;
  schedule: string;       // cron expression
  last_run_at?: string;
  last_status: "success" | "failed" | "running" | "never";
  last_error?: string;
  next_run_at?: string;
}
```

---

### 15.3 Integration Health

**Route:** `/system/health` | **File:** `_admin.system.health.tsx`

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 15.8 | `GET` | `/system/health` | Status of Nimbus, WhatsApp, FCM, Postmark — **no secret values** |

```ts
{
  integrations: [
    {
      name: "nimbus_sms" | "whatsapp" | "fcm" | "postmark";
      status: "healthy" | "degraded" | "down" | "not_configured";
      last_checked_at: string;
      message?: string;
    }
  ]
}
```

---

### 15.4 Audit Log

**Route:** `/system/audit` | **File:** `_admin.system.audit.tsx`

| # | Method | Endpoint | Query |
|---|--------|----------|-------|
| 15.9 | `GET` | `/audit-log` | `page`, `page_size`, `action`, `admin_id`, `date_from`, `date_to` |

```ts
{
  id: number;
  admin_id: number;
  admin_email: string;
  action: "suspend" | "unsuspend" | "refund" | "plan_change" | "subscription_edit" | "admin_create" | ...;
  target_type: string;
  target_id: number;
  metadata?: Record<string, unknown>;
  ip_address?: string;
  created_at: string;
}
```

---

## 16. Shared Data Models

Reference types used across multiple endpoints:

### `SellerSettings`

```ts
{
  reminder_channels: ("sms" | "whatsapp" | "push")[];
  auto_remind_enabled: boolean;
  auto_remind_days_before: number;
  daily_summary_enabled: boolean;
  daily_summary_time: string;   // "09:00"
  push_enabled: boolean;
}
```

### `TeamMember`

```ts
{
  id: number;
  seller_id: number;
  name: string;
  email?: string;
  phone?: string;
  role: "owner" | "staff";
  status: "active" | "inactive";
  created_at: string;
}
```

### `SellerNotification`

```ts
{
  id: number;
  seller_id: number;
  type: "daily_summary" | "overdue_alert" | "payment_received" | "system";
  title: string;
  body: string;
  channel: "push" | "email" | "in_app";
  status: "sent" | "failed";
  created_at: string;
}
```

### `SellerDeviceToken` / `CustomerDeviceToken`

```ts
{
  id: number;
  device_name?: string;
  platform: "android" | "ios" | "web";
  fcm_token_preview: string;   // masked
  last_active_at: string;
  created_at: string;
}
```

---

## 17. Master Endpoint Index

**Total: 95+ endpoints** (including implied write actions).

### Auth (4)
`POST /auth/login` · `GET /auth/me` · `POST /auth/refresh` · `POST /auth/logout`

### Global (3)
`GET /search` · `GET /notifications` · `PATCH /notifications/{id}`

### Dashboard (6)
`GET /dashboard/stats` · `GET /dashboard/charts/collections` · `GET /dashboard/charts/signups` · `GET /dashboard/charts/outstanding-by-status` · `GET /dashboard/activity` · `GET /dashboard/export`

### Sellers (16)
`GET /sellers` · `GET /sellers/export` · `POST /sellers/invite` · `GET /sellers/{id}` · `GET /sellers/{id}/summary` · `PATCH /sellers/{id}` · `POST /sellers/{id}/reset-password` · `POST /sellers/{id}/suspend` · `POST /sellers/{id}/unsuspend` · `GET /sellers/{id}/settings` · `PATCH /sellers/{id}/settings` · `GET /sellers/{id}/customers` · `GET /sellers/{id}/customers/export` · `GET /sellers/{id}/team` · `GET /sellers/{id}/notifications` · `GET /sellers/{id}/devices`

### Customers (11)
`GET /customers` · `GET /customers/export` · `GET /customers/{id}` · `PATCH /customers/{id}` · `POST /customers/{id}/reset-password` · `POST /customers/{id}/suspend` · `POST /customers/{id}/unsuspend` · `GET /customers/{id}/accounts` · `GET /customers/{id}/payments` · `GET /customers/{id}/notifications` · `GET /customers/{id}/messages` · `GET /customers/{id}/devices`

### Team (1)
`GET /team-members`

### Subscriptions (12)
`GET /subscriptions` · `POST /subscriptions/{id}/cancel` · `PATCH /subscriptions/{id}` · `GET /subscriptions/plans` · `POST /subscriptions/plans` · `PATCH /subscriptions/plans/{id}` · `DELETE /subscriptions/plans/{id}` · `GET /trials` · `POST /trials/{id}/extend` · `POST /trials/{id}/convert` · `POST /trials/{id}/expire` · `GET /subscriptions/invoices` · `GET /subscriptions/invoices/{id}/download`

### Payments (2)
`GET /payments` · `POST /payments/{id}/refund`

### Transactions (5)
`GET /transactions` · `GET /transactions/sync-queue` · `POST /transactions/sync-queue/{id}/retry` · `POST /transactions/sync-queue/{id}/dismiss`

### Communications (6)
`GET /reminder-logs` · `POST /reminder-logs/{id}/resend` · `GET /otp-records`

### Promos (5)
`GET /promo-codes` · `POST /promo-codes` · `PATCH /promo-codes/{id}` · `DELETE /promo-codes/{id}` · `GET /promo-redemptions`

### Shops (3)
`GET /seller-customers` · `GET /customer-accounts` · `GET /sellers?view=business`

### Moderation (6)
`GET /suspensions` · `GET /messages` · `POST /messages/{id}/flag` · `DELETE /messages/{id}` · `GET /tickets` · `PATCH /tickets/{id}` · `POST /tickets/{id}/replies`

### Reports (4)
`GET /reports/collections` · `GET /reports/overdue` · `GET /reports/daily-summary` · `GET /reports/export`

### System (9)
`GET /system/admins` · `POST /system/admins` · `PATCH /system/admins/{id}` · `DELETE /system/admins/{id}` · `POST /system/admins/{id}/reset-password` · `GET /system/cron` · `POST /system/cron/{job}/trigger` · `GET /system/health` · `GET /audit-log`

---

## 18. Implementation Status

| Status | Routes / features |
|--------|-------------------|
| **API call wired in frontend** | `/login`, `/` (dashboard stats + 2 charts), `/sellers` (list), `/customers` (list) |
| **UI scaffolded — endpoint named in code** | All other 28 admin sub-routes (ComingSoon placeholders) |
| **Buttons visible but no handler** | Dashboard date range & export, sellers filters (status/subscription), pagination Next/Prev, all row dropdown actions, seller/customer detail header buttons, global search, notification bell |
| **Phase 2 (noted in UI copy)** | Help tickets, chat moderation flag/delete |

### Recommended build order for backend

1. **Auth** (§2) — unblock login and session
2. **Dashboard** (§4) — stats + charts + activity
3. **Sellers & Customers** lists + detail tabs (§5, §6)
4. **Transactions & Shops** (§9, §12) — core ledger data
5. **Communications** (§10) — reminder/SMS logs
6. **Subscriptions & Reports** (§8, §14)
7. **System & Moderation** (§15, §13)

---

*Generated from `udhar-insight-hub` frontend source — covers all 36 admin route files, login, auth provider, top bar, and sidebar navigation.*
