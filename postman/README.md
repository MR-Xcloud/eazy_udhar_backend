# EazyUdhar Admin API — Postman Collection

## Files

| File | Purpose |
|------|---------|
| `EazyUdhar_Admin_API.postman_collection.json` | Full collection (98 requests, all admin endpoints) |
| `EazyUdhar_Admin_Local.postman_environment.json` | Local dev environment variables |
| `generate_admin_collection.py` | Regenerate collection after URL changes |

## Import into Postman

1. Open Postman → **Import**
2. Select both JSON files in this folder
3. Choose environment **EazyUdhar Admin — Local** (top-right)
4. Run **1. Auth → Login** — `access_token` is saved automatically
5. Run any other request

## Regenerate collection

After changing `adminapp/urls.py`:

```bash
python postman/generate_admin_collection.py
```

## Base URL

Default: `http://192.168.0.145:8099/admin-api/v1`

Update `base_url` in collection or environment variables to match your server.

## Seed admin (first run)

```bash
python manage.py seed_admin_data
```

Credentials: `admin@eazyudhar.com` / `Admin@2026`
