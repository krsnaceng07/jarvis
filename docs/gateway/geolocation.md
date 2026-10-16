# Geolocation Route (`/plugins/geolocation/lookup`)

The bundled `geolocation` plugin registers `GET /plugins/geolocation/lookup?ip=<address>` on the Gateway HTTP server.

## Overview

- **Route:** `GET /plugins/geolocation/lookup?ip=<address>`
- **Authentication:** Gateway HTTP Bearer token (`auth: "gateway"`)
- **Default Database:** DB-IP City Lite (`.mmdb.gz`)
- **Attribution:** Included in every response (`{"text": "IP Geolocation by DB-IP", "url": "https://db-ip.com"}`)

## Request

```http
GET /plugins/geolocation/lookup?ip=8.8.8.8 HTTP/1.1
Host: 127.0.0.1:18789
Authorization: Bearer <GATEWAY_TOKEN>
```

## Responses

### 200 OK — Found Location
```json
{
  "found": true,
  "city": "Mountain View",
  "region": "California",
  "country": "United States",
  "countryCode": "US",
  "attribution": {
    "text": "IP Geolocation by DB-IP",
    "url": "https://db-ip.com"
  }
}
```

### 200 OK — Private, Loopback, CGNAT or Unplaced Address
```json
{
  "found": false,
  "attribution": {
    "text": "IP Geolocation by DB-IP",
    "url": "https://db-ip.com"
  }
}
```

### 400 Bad Request — Invalid IP
```json
{
  "error": "ip must be a valid IPv4 or IPv6 address"
}
```

### 503 Service Unavailable — Database Outage
```json
{
  "error": "geolocation database unavailable"
}
```

## Security & Privacy
- **Local Resolution Only**: IP addresses are never transmitted to third-party endpoints.
- **Fast-fail on non-routable IPs**: Loopback (`127.0.0.1`), LAN (`10.0.0.0/8`, `192.168.0.0/16`), and CGNAT (`100.64.0.0/10`) immediately answer `found: false` without loading the database.
