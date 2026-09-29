# The GST portal's Search Taxpayer flow — as measured

**Measured 29 September 2026**, from Manas's laptop on an Indian residential
connection, by the GSTIN auto-fill pass (ABOUT.md §5 `/address`,
`gst_lookup.py`). Everything below was **read from the portal's own page and
observed on the wire**, not guessed. Nothing here was proved from the
production server — see §6.

**The rules the discovery ran under**, and the application follows the same
ones: a human types every CAPTCHA (nothing read, decoded or solved it — the two
images were opened in Manas's image viewer and never looked at by the tooling);
an honest User-Agent naming this application; no Referer, no Origin, no browser
impersonation, no timing tricks.

---

## 1. Where the request comes from

The Search Taxpayer page, `https://services.gst.gov.in/services/searchtp`, is an
AngularJS shell. The pre-login search view is
`/pages/services/searchtaxpayer_pre.html`, controller `searchtpctrl` in
`https://static.gst.gov.in/uiassets/js/services/searchtpCtrl1.0.js`.

| What | Read from | Finding |
|---|---|---|
| The submit | `searchtaxpayer_pre.html` | `<form name="searchtaxp" data-ng-submit="searchTaxpayerpreLogin();">` |
| The request | `searchtpCtrl1.0.js`, `searchTaxpayerpreLogin()` | `ajax.post("/services/api/search/taxpayerDetails", {"gstin", "captcha"})` |
| The CAPTCHA | `directives2.0.js`, directive `captcha` | `scope.captcha_url = "/services/captcha?rnd=" + Math.random()` (an audio CAPTCHA exists at `/services/audiocaptcha`; not used) |
| The CAPTCHA format | `directives2.0.js`, `validations.formats` | `captcha: /^([0-9]){6}$/` — six digits |
| Headers added | `directives2.0.js`, service `ajax` + interceptors `httpTimeout` / `httpInterceptor` | only an `at` header, and only when an earlier response set one (never, before login). The interceptors add a 20 s client timeout and nothing else |
| Error handling | `searchtpCtrl1.0.js` | `SWEB_9000` → invalid CAPTCHA; `SWEB_9032` / `SWEB_9035` → invalid GSTIN; `SWEB_9034` → mandatory field missing; `SWEB_9021` / `SWEB_8000` → a message from the translation table. Checked **both** as `response.errorCode` and as `response.error.error_cd` |

An older function in the same controller, `searchTaxpayerpre()`, posts the same
body to `/services/api/search/tp`. The page's form does not call it; it was not
used.

---

## 2. The exchange

```
GET  https://services.gst.gov.in/services/captcha?rnd=<random>
     → 200 image/png, 4,737–4,972 bytes (three fetches)
       Set-Cookie: CaptchaCookie=…   Set-Cookie: TS0134d082=…

POST https://services.gst.gov.in/services/api/search/taxpayerDetails
     Content-Type: application/json;charset=utf-8
     Accept: application/json, text/plain, */*
     Cookie: CaptchaCookie=…; TS0134d082=…
     {"gstin": "<15 characters>", "captcha": "<6 digits, typed by a human>"}
     → 200 application/json;charset=ISO-8859-1
       Set-Cookie: CaptchaCookie=…   (rotated — one CAPTCHA, one search)
```

| Question the brief asked | Answer, measured |
|---|---|
| Method | `POST` |
| Payload | JSON, exactly two keys: `gstin`, `captcha` |
| Cookies | `CaptchaCookie` and `TS0134d082`, both set by the CAPTCHA response |
| Headers | none beyond the JSON content type. **No Referer, no Origin, no `at`, no browser User-Agent** was sent, and every request that was answered was answered |
| Does the page have to be loaded first? | **No.** A fresh cookie jar that fetched only the CAPTCHA searched successfully (attempt 5 below) |
| Anything beyond cookies + CAPTCHA? | **No.** The brief's stop condition was not met |
| Charset | the body is labelled `ISO-8859-1`. `gst_lookup._json_object()` tries UTF-8 first (JSON is UTF-8 by definition) and Latin-1 second |

---

## 3. The three responses

### Found — Samruddhi's own GSTIN, `27BGRPB0456K1Z7`

HTTP 200, 723 characters, 0.69 s. **The keys are exact; personal values are
redacted to their shape**, because this registration is a proprietorship and
its legal name and principal place of business are a person's.

```json
{
  "ntcrbs": "SPO",
  "adhrVFlag": "No",
  "lgnm": "<legal name — for a proprietorship, the proprietor's own name>",
  "stj": "State - Maharashtra,Zone - …,Division - …,Charge - … (Jurisdictional Office)",
  "dty": "Regular",
  "cxdt": "",
  "gstin": "27BGRPB0456K1Z7",
  "nba": ["Wholesale Business", "Retail Business", "Works Contract"],
  "ekycVFlag": "No",
  "cmpRt": "NA",
  "rgdt": "dd/mm/yyyy",
  "ctb": "Proprietorship",
  "pradr": {
    "adr": "<floor>, <number>, <building>, <street>, <locality>, <locality>, <city>, <district>, Maharashtra, <PIN>"
  },
  "sts": "Active",
  "tradeNam": "SAMRUDDHI ENTERPRISES/SAMRUDDHI FIRE",
  "isFieldVisitConducted": "No",
  "ctj": "State - CBIC,Zone - …,Commissionerate - …,Division - …,Range - …",
  "einvoiceStatus": "No"
}
```

⚠ **`pradr` carries ONE key, `adr` — a single comma-joined string.** There is
no structured `addr` object (no building, street, city or PIN keys). The
address has to be split, and `gst_lookup.split_address()` says what it reads
with confidence and what it guesses. The measured string had ten parts.

### Wrong CAPTCHA — deliberately `000000`, never shown to anybody

HTTP 200, verbatim:

```json
{"url": "/", "message": null, "errorCode": "SWEB_9000"}
```

### Invalid GSTIN — `27ZZZZZ9999Z1Z8`, check-valid and invented

HTTP 200, verbatim — **a different envelope** from the one above, which is
why `gst_lookup._error_codes()` reads both:

```json
{"status_cd": "0", "error": {"message": "Invalid GSTIN / UID", "error_cd": "SWEB_9035"}, "cmpRt": "NA"}
```

---

## 4. Field mapping — from the response above, not from a guess

| Portal key | `gst_lookup` result | Address form |
|---|---|---|
| `lgnm` | `legal_name` | shown; the **company** only when there is no trade name |
| `tradeNam` | `trade_name` | **company**; the **label** too while the label is blank (not for a site) |
| `sts` | `status`, `active` (= `"Active"`) | anything but `Active` → red banner + required acknowledgement; stamped on the record at save as `gst_status` |
| `ctb` | `constitution` | shown |
| `dty` | `taxpayer_type` | shown |
| `rgdt` (`dd/mm/yyyy`) | `registration_date` (`YYYY-MM-DD`) | shown |
| `cxdt` | `cancellation_date` | kept in the cache |
| `pradr.adr` | `address_text`, and `address` = its split | shown verbatim; line 1, line 2, city, PIN and State filled from the split — **never for a site** |
| `gstin` | must equal the GSTIN asked for, or the answer is refused as a shape mismatch | — |
| (the GSTIN itself) | `state` from its first two digits | the State box, on the 15th character, before any lookup |

Not used: `ntcrbs`, `adhrVFlag`, `ekycVFlag`, `cmpRt`, `nba`, `stj`, `ctj`,
`isFieldVisitConducted`, `einvoiceStatus`. **The shape test** — the fallback's
trigger — requires `gstin`, `lgnm`, `sts` and `pradr.adr` and is lenient about
everything else.

---

## 5. Reliability, as measured — and what it means for one attempt

Every request made to `services.gst.gov.in`, in order:

| # | Request | Outcome |
|---|---|---|
| 1 | page | 200 |
| 2 | view template, no cookie | **dropped** (connection closed, no response) |
| 3 | view template, with the page's cookie | 200 |
| 4–6 | page · CAPTCHA · search with `000000` | 200 · 200 · 200 `SWEB_9000` |
| 7–8 | page · CAPTCHA | 200 · **dropped** |
| 9–10 | page · CAPTCHA | 200 · **dropped** |
| 11–13 | (after backing off ~10 minutes) page · CAPTCHA · **search with Manas's answer** | 200 · 200 · **200, the record above — human attempt 1** |
| 14 | page | **dropped** |
| 15 | CAPTCHA only, fresh jar | 200 |
| 16 | search with Manas's second answer | **dropped** |
| 17 | the same search, resent once | 200 `SWEB_9035` — human attempt 2 |

**5 of 17 dropped (29%)**, in bursts. Answered requests took **0.4–1.1 s**.
Static assets on `static.gst.gov.in`: 5 of 5 answered. Two human CAPTCHAs were
used, both typed correctly first time.

⚠ **The application does not retry** — the brief's rule, and the single worker
thread is why (ABOUT.md §5 `/address`). At the rate measured here, roughly one
lookup in three to one in five will say *"Auto-fill unavailable, enter
manually."* and the user presses *refresh* or types. Whether the drops were
throttling of this laptop's burst of probes or are the portal's normal
behaviour was not established.

---

## 6. ⚠ Production reachability is UNPROVEN

Everything above was measured from an **Indian residential IP**. Whether the
production server can reach `services.gst.gov.in` at all — a cloud or
datacentre address, possibly outside India, possibly behind an egress firewall
— **has not been tested**. Run this **on the production box** before relying on
the feature:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 'https://services.gst.gov.in/services/captcha?rnd=0.1'
```

**Reachable** = an HTTP status is printed (`200`). **Blocked** = `403`, or a
timeout (`000` and curl exit 28). The image is written to `/dev/null`; nobody
reads it. A single `000` can be one of the drops in §5 — run it three times.

If it is blocked, the feature degrades to what it was before this pass: the
offline check still runs, and every lookup says *"Auto-fill unavailable, enter
manually."* — after a **5-second** stall on the single worker thread each time.

---

## 7. The fallback — gstinapi.in (optional, `GST_API_KEY`)

Read from `https://gstinapi.in/` and `https://gstinapi.in/docs` the same day:
`GET https://www.gstinapi.in/v1/gstin/{gstin}` with the key in an `x-api-key`
header; 200 success, 404 not registered, 400/401/402/403/429/502 failures; 60
requests a minute; one credit per success; a test GSTIN `00AAAAA0000A1ZT`.

⚠ **The two pages disagree about the envelope** — the home page shows a flat
object, the reference wraps it as `{"success": true, …, "data": {…}}` — so
`gst_lookup._from_fallback()` accepts both and treats anything else as a shape
mismatch. The reference documents `address` as a string without State or PIN
and a separate `pincode`; the adapter appends them so one splitter reads both
sources.

**Measured without a key** (both hosts): HTTP 401,
`{"error": "API key required. Pass x-api-key header.", "fix": "Create a key at https://www.gstinapi.in/api-keys and send it as the x-api-key header."}`
— no `success` key at all, contrary to the reference.

⚠ **The success path is UNPROVEN**: no key was available, so no successful
response was ever seen. It is tested only against the documented shapes.
