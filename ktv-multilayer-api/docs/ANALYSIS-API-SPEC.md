# Averos — Spesifikasi FastAPI Analysis API

Dokumen ini menjelaskan kontrak yang **wajib dipenuhi** oleh backend FastAPI
eksternal (analisis EUDR) agar web app Averos (Next.js, repo ini) bisa langsung
memakainya **tanpa mengubah kode frontend**.

Sumber kontrak di kode:
[`app/api/analysis/[type]/route.ts`](../app/api/analysis/[type]/route.ts) (proxy),
[`lib/analysisClient.ts`](../lib/analysisClient.ts) (mapping response),
[`lib/geo.ts`](../lib/geo.ts) (`plotsFromValidation`).

---

## Daftar isi

1. [Alur pemanggilan](#1-alur-pemanggilan)
2. [Aturan umum](#2-aturan-umum-berlaku-untuk-semua-endpoint)
3. [`POST /api/v1/validate-geometry`](#3-post-apiv1validate-geometry)
4. [`POST /api/v1/deforestation`](#4-post-apiv1deforestation)
5. [`POST /api/v1/protected-area`](#5-post-apiv1protected-area-land-legality)
6. [`POST /api/v1/rainfall`](#6-post-apiv1rainfall)
7. [`POST /api/v1/ghg-emission`](#7-post-apiv1ghg-emission)
8. [Cara test dengan curl](#8-cara-test-dengan-curl)
9. [Checklist](#9-checklist)
10. [Opsional / saran](#10-opsional--saran)

---

## 1. Alur pemanggilan

```
Browser ──► Next.js  POST /api/analysis/{type}   (cek login + kuota/billing)
                │
                └──► FastAPI  POST {ANALYSIS_API_BASE}/api/v1/{type}
                          │
                          └──► Google Earth Engine / dataset (GFW, JRC, SBTN, WDPA, curah hujan)
```

Urutan dari sisi user:

1. User upload GeoJSON / gambar polygon → app memanggil **`validate-geometry`**
   untuk **semua** plot.
2. Plot yang lolos validasi (valid) → user memilih analisis → app memanggil
   endpoint analisis yang dipilih **secara paralel** (maks. 4 sekaligus) dengan
   file GeoJSON yang sama:
   `deforestation`, `protected-area`, `rainfall`, `ghg-emission`.
3. Hasil tiap endpoint digabung ke tiap plot berdasarkan `plot_id`
   (fallback: berdasarkan urutan).

| `{type}` di URL | Nama di UI | Kunci di frontend |
|---|---|---|
| `validate-geometry` | Geometry Checker | — |
| `deforestation` | Deforestation Analysis | `deforestation` |
| `protected-area` | Land Legality Analysis | `legality` |
| `rainfall` | Rainfall | `rainfall` |
| `ghg-emission` | GHG Emission | `ghg` |

---

## 2. Aturan umum (berlaku untuk semua endpoint)

### 2.1 Base URL

Diset di env server Next.js:

```env
ANALYSIS_API_BASE=https://api-kamu.com
```

Isi **root saja** (tanpa `/api/v1`, tanpa trailing slash). App yang
menambahkan `/api/v1/{type}`.

### 2.2 Request

```
POST /api/v1/{type}
Content-Type: multipart/form-data
```

| Field form | Tipe | Keterangan |
|---|---|---|
| `file` | file | GeoJSON, filename `plots.geojson` (atau nama file upload user), content-type `application/geo+json` |

Signature FastAPI:

```python
from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.post("/api/v1/deforestation")
async def deforestation(file: UploadFile = File(...)):
    fc = json.loads(await file.read())
    ...
```

> Butuh paket `python-multipart` agar `UploadFile` jalan.

### 2.3 Isi file GeoJSON (input)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "plot_id": "plot-0", "name": "Kebun A" },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [96.906847, 4.759811],
          [96.905778, 4.759878],
          [96.905790, 4.760102],
          [96.906856, 4.760043],
          [96.906847, 4.759811]
        ]]
      }
    }
  ]
}
```

Jaminan dari sisi app:

- `geometry.type` **selalu `Polygon`** dengan **1 ring** (MultiPolygon sudah
  dipecah oleh frontend menjadi beberapa feature).
- Ring sudah **tertutup** (titik pertama = titik terakhir).
- Koordinat `[longitude, latitude]`, EPSG:4326.
- `properties` hanya berisi `plot_id` (string, mis. `"plot-0"`, `"plot-1"`, …)
  dan `name` (string).
- Jumlah plot per request: **1 – 1000**. Maks. **2000 titik** per plot.
- Untuk endpoint analisis (selain `validate-geometry`), app **hanya mengirim
  plot valid** (tidak self-intersect, tidak duplicate vertex, luas > 0).
- Untuk `validate-geometry`, input **bisa berisi polygon rusak**.

### 2.4 Response sukses

HTTP **200**, `Content-Type: application/json`:

```json
{
  "data": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[ ... ]] },
        "properties": { "plot_id": "plot-0", "...": "..." }
      }
    ]
  }
}
```

**Wajib:**

1. Envelope **`{ "data": FeatureCollection }`** — app membaca `data.features`.
2. **Satu feature output per feature input, urutan sama.**
3. **Kembalikan `plot_id` dari input apa adanya** (backend lama mengembalikan
   `"unknown"`, sehingga app terpaksa mencocokkan berdasarkan posisi).
4. Nama field **persis** seperti tabel di tiap endpoint (snake_case).
   Field tambahan boleh, akan diabaikan.

### 2.5 Error

- Gagal → kembalikan status **non-2xx** (400 / 422 / 500 / 503).
  Body bebas, mis. `{ "detail": "Earth Engine not authorized" }`.
- Efek di app: analisis tersebut ditandai gagal dan UI menampilkan
  *"Not analyzed yet"*. Analisis lain tetap jalan.
- Status dan body dari FastAPI diteruskan apa adanya oleh proxy ke browser.

### 2.6 Performa

- **Timeout: 110 detik** per request (seluruh batch). Lewat dari itu app
  membalas `502 Upstream analysis service unavailable`.
- App memanggil sampai **4 endpoint paralel** untuk batch yang sama — backend
  harus sanggup melayani request bersamaan (mis. `uvicorn --workers N` atau
  proses async).

### 2.7 Yang TIDAK perlu

- **CORS** — dipanggil server-to-server dari Next.js, bukan dari browser.
- **Auth** — saat ini app tidak mengirim header auth (lihat
  [bagian 10](#10-opsional--saran)).
- Endpoint lain (list, history, dsb.) — tidak dipakai app.

---

## 3. `POST /api/v1/validate-geometry`

Cek kualitas polygon. Tidak memotong kuota user. Jika endpoint ini gagal, app
memakai pengecekan lokal (jadi tidak fatal, tapi sebaiknya tetap jalan).

**Backend tidak boleh crash** untuk polygon rusak — tetap kembalikan feature
dengan flag yang sesuai.

### Field `properties` output

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `plot_id` | string | ✅ | dari input |
| `name` | string | ✅ | dari input |
| `area_sqm` | number | ✅ | luas dalam **m²** (app membagi 10.000 → ha). Jika `0`/kosong, app menghitung sendiri |
| `zero_area` | bool | ✅ | luas ≈ 0 |
| `self_intersection` | bool | ✅ | garis batas saling memotong |
| `not_ring` | bool | ✅ | ring tidak tertutup / kurang dari 4 titik |
| `duplicate_vertices` | bool | ❌ | diabaikan — app menghitung sendiri |

> ⚠️ **`geometry` wajib dikembalikan** (Polygon yang sama dengan input).
> App membaca bentuk plot dari `geometry.coordinates[0]` response ini.

Plot dianggap **valid** oleh app jika `zero_area`, `self_intersection`,
`not_ring` semuanya `false` (dan tidak ada duplicate vertex menurut cek lokal).

### Contoh response

```json
{
  "data": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[96.906847,4.759811],[96.905778,4.759878],[96.90579,4.760102],[96.906856,4.760043],[96.906847,4.759811]]]
        },
        "properties": {
          "plot_id": "plot-0",
          "name": "Kebun A",
          "area_sqm": 2950.4,
          "zero_area": false,
          "self_intersection": false,
          "not_ring": false
        }
      }
    ]
  }
}
```

---

## 4. `POST /api/v1/deforestation`

Deteksi kehilangan tutupan hutan di dalam plot dari 3 dataset: **GFW**, **JRC**,
**SBTN**. Untuk EUDR, umumnya yang dihitung adalah loss **setelah cutoff
31 Desember 2020**.

### Field `properties` output

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `plot_id` | string | — | dari input |
| `overall_compliance.overall_risk` | string | — | `"high"` → UI: **Loss detected** / badge risiko tinggi. Nilai lain (`"low"`, dll.) → **No loss detected**. Tidak case-sensitive |
| `gfw_loss.gfw_loss_area` | number | **ha** | luas loss menurut GFW |
| `gfw_loss.gfw_loss_percent` | number | **0–100** | ditampilkan "X% of plot" |
| `jrc_loss.jrc_loss_area` | number | ha | |
| `jrc_loss.jrc_loss_percent` | number | 0–100 | |
| `sbtn_loss.sbtn_loss_area` | number | ha | |
| `sbtn_loss.sbtn_loss_percent` | number | 0–100 | |

Format datar juga diterima (fallback): `risk_level`, `gfw_loss_area_ha`,
`gfw_loss_percent`, `jrc_loss_area_ha`, `jrc_loss_percent`,
`sbtn_loss_area_ha`, `sbtn_loss_percent`. **Disarankan pakai format bersarang
di atas.**

### Contoh `properties`

```json
{
  "plot_id": "plot-0",
  "overall_compliance": { "overall_risk": "low" },
  "gfw_loss":  { "gfw_loss_area": 0.12, "gfw_loss_percent": 9.9 },
  "jrc_loss":  { "jrc_loss_area": 0.0,  "jrc_loss_percent": 0.0 },
  "sbtn_loss": { "sbtn_loss_area": 0.0, "sbtn_loss_percent": 0.0 }
}
```

---

## 5. `POST /api/v1/protected-area` (Land Legality)

Cek overlap plot dengan kawasan lindung (**WDPA**).

### Field `properties` output

| Field | Tipe | Keterangan |
|---|---|---|
| `plot_id` | string | dari input |
| `wdpa_status` | string | lihat tabel nilai di bawah |
| `wdpa_categories` | string[] | kategori IUCN / nama kawasan yang overlap. `[]` jika tidak ada |

| `wdpa_status` | Tampilan UI |
|---|---|
| `"non_compliant"` | **Non-Compliant** — overlap dengan kawasan lindung |
| `"indicative"` | **Review** — indikasi overlap / perlu dicek |
| nilai lain (disarankan `"compliant"`) | **Compliant** |

### Contoh `properties`

```json
{
  "plot_id": "plot-0",
  "wdpa_status": "compliant",
  "wdpa_categories": []
}
```

---

## 6. `POST /api/v1/rainfall`

Statistik **curah hujan tahunan** di area plot.

### Field `properties` output

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `plot_id` | string | — | dari input |
| `rainfall_mean_mm` | number | mm | rata-rata curah hujan tahunan di plot |
| `rainfall_min_mm` | number | mm | minimum di plot |
| `rainfall_max_mm` | number | mm | maksimum di plot |
| `rainfall_std_mm` | number | mm | standar deviasi (ditampilkan "±X mm") |
| `area_hectares` | number | ha | luas plot |
| `analysis_period.start_date` | string | — | ditampilkan apa adanya; disarankan `YYYY-MM-DD` |
| `analysis_period.end_date` | string | — | idem |

`analysis_period` opsional, tapi disarankan (muncul di teks banner UI).

### Contoh `properties`

```json
{
  "plot_id": "plot-0",
  "rainfall_mean_mm": 2450.3,
  "rainfall_min_mm": 2300.1,
  "rainfall_max_mm": 2600.8,
  "rainfall_std_mm": 45.2,
  "area_hectares": 0.3,
  "analysis_period": { "start_date": "2024-01-01", "end_date": "2024-12-31" }
}
```

---

## 7. `POST /api/v1/ghg-emission`

Estimasi emisi gas rumah kaca dari loss tutupan hutan, per dataset.

### Field `properties` output

| Field | Tipe | Satuan | Keterangan |
|---|---|---|---|
| `plot_id` | string | — | dari input |
| `gfw_ghg_emission.area_hectares` | number | ha | |
| `gfw_ghg_emission.net_emission_tco2e` | number | tCO₂e | |
| `jrc_ghg_emission.area_hectares` | number | ha | |
| `jrc_ghg_emission.net_emission_tco2e` | number | tCO₂e | |
| `sbtn_ghg_emission.area_hectares` | number | ha | |
| `sbtn_ghg_emission.net_emission_tco2e` | number | tCO₂e | |
| `total_net_emission_tco2e` | number | tCO₂e | **opsional**. Jika tidak ada, app memakai nilai **terbesar** dari GFW/JRC/SBTN |

### Contoh `properties`

```json
{
  "plot_id": "plot-0",
  "gfw_ghg_emission":  { "area_hectares": 0.12, "net_emission_tco2e": 35.1 },
  "jrc_ghg_emission":  { "area_hectares": 0.0,  "net_emission_tco2e": 0 },
  "sbtn_ghg_emission": { "area_hectares": 0.0,  "net_emission_tco2e": 0 },
  "total_net_emission_tco2e": 35.1
}
```

---

## 8. Cara test dengan curl

Buat file test dengan format persis seperti yang dikirim app (2 plot):

```bash
cat > test.geojson <<'EOF'
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "plot_id": "plot-0", "name": "BENER-MERIAH-002" },
      "geometry": { "type": "Polygon", "coordinates": [[[96.906847,4.759811],[96.905778,4.759878],[96.90579,4.760102],[96.906856,4.760043],[96.906847,4.759811]]] }
    },
    {
      "type": "Feature",
      "properties": { "plot_id": "plot-1", "name": "BENER-MERIAH-003" },
      "geometry": { "type": "Polygon", "coordinates": [[[96.900937,4.767424],[96.901633,4.767234],[96.901382,4.766749],[96.900729,4.766899],[96.900937,4.767424]]] }
    }
  ]
}
EOF
```

Panggil tiap endpoint (cara kirimnya sama seperti Next.js):

```bash
BASE=https://api-kamu.com
for t in validate-geometry deforestation protected-area rainfall ghg-emission; do
  echo "== $t"
  curl -sS -w "\nHTTP %{http_code} in %{time_total}s\n" \
    -F "file=@test.geojson;type=application/geo+json;filename=plots.geojson" \
    "$BASE/api/v1/$t"
done
```

Yang dicek di output:

- HTTP 200 dan waktu < 110 detik.
- Ada `data.features` dengan **2 feature**, urutan `plot-0`, `plot-1`.
- `plot_id` sama dengan input (bukan `"unknown"`).
- Nama field sesuai tabel di dokumen ini.

> File di folder `data/*.geojson` repo ini sebagian besar berisi
> **MultiPolygon** tanpa `plot_id` — itu format upload user, **bukan** format
> yang dikirim app ke backend. Untuk test backend, pakai format di atas.

---

## 9. Checklist

- [ ] 5 endpoint: `POST /api/v1/validate-geometry`, `/deforestation`,
      `/protected-area`, `/rainfall`, `/ghg-emission`
- [ ] Menerima `multipart/form-data` field **`file`**
- [ ] Response dibungkus **`{ "data": FeatureCollection }`**
- [ ] Jumlah & urutan feature output = input; **`plot_id` dikembalikan**
- [ ] `validate-geometry` mengembalikan **`geometry`** dan tidak crash untuk polygon rusak
- [ ] Nama field persis seperti tabel (snake_case)
- [ ] Satuan: **ha**, **m²** (hanya `area_sqm`), persen **0–100**, **mm**, **tCO₂e**
- [ ] Nilai enum: `overall_risk` = `"high"` / `"low"`;
      `wdpa_status` = `"non_compliant"` / `"indicative"` / `"compliant"`
- [ ] Error → status non-2xx
- [ ] < 110 detik per batch (sampai 1000 plot); tahan 4 request paralel
- [ ] Earth Engine service account sudah terautentikasi di server
- [ ] Setelah deploy: set `ANALYSIS_API_BASE` di `.env` server Next.js, lalu restart app

---

## 10. Opsional / saran

- **`GET /health`** → `{"status":"ok"}` untuk monitoring / uptime check
  (tidak dipakai app).
- **API key.** Saat ini backend harus terbuka (tanpa auth) karena app tidak
  mengirim header apa pun. Opsi pengamanan:
  - Batasi akses lewat firewall: hanya IP server Next.js yang boleh masuk; atau
  - Tambah header `X-API-Key` — butuh perubahan kecil di
    [`app/api/analysis/[type]/route.ts`](../app/api/analysis/[type]/route.ts)
    (kirim header dari env baru, mis. `ANALYSIS_API_KEY`).
- **Batas ukuran upload** di reverse proxy (nginx `client_max_body_size`):
  plot biasa (±50 titik) × 1000 plot ≈ 2 MB, tapi batas teoretis
  (1000 plot × 2000 titik) ≈ 80 MB. Set sesuai kebutuhan, mis. **20–100 MB**.
