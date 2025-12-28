# Panduan Lengkap: Menggunakan API EUDR dengan 20 Data GeoJSON

## 📁 File yang Sudah Dibuat

1. **`example_geojson_20_plots.json`** - Contoh GeoJSON dengan 20 polygon
2. **`test_bulk_geojson.py`** - Script Python untuk testing API

## 🚀 Cara Menggunakan

### 1. Pastikan API Server Running

```bash
# Aktifkan environment dan start server
cd d:\b_outside\h_humid_backend\eudr\ktv-multilayer-api
python app.py
```

### 2. Install Dependencies (jika perlu)

```bash
pip install requests
```

### 3. Jalankan Test Script

```bash
python test_bulk_geojson.py
```

## 📊 Format Request yang Benar

### Endpoint untuk Bulk GeoJSON:
```
POST /api/v1/process-geojson
```

### Request Body Format:
```json
{
  "geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "plot_id": "PLOT_001",
          "country_name": "Central African Republic",
          "farm_name": "Forestry Concession Central",
          "area_ha": 15.7
        },
        "geometry": {
          "type": "Polygon",
          "coordinates": [[...]]
        }
      }
    ]
  }
}
```

## ⚡ Parallel Processing

API Anda akan secara otomatis:
- Menggunakan 16 service accounts dengan round-robin distribution
- Memproses maksimal 8 features secara bersamaan
- Mengembalikan hasil yang sudah diurutkan sesuai input

## 📈 Expected Response

```json
{
  "message": "Bulk GeoJSON processing completed successfully",
  "total_features": 20,
  "parallel_processing_enabled": true,
  "accounts_used": 16,
  "processing_time_seconds": 45.67,
  "results": [
    {
      "feature_index": 0,
      "input_properties": {
        "plot_id": "PLOT_001",
        "country_name": "Central African Republic",
        "farm_name": "Forestry Concession Central",
        "area_ha": 15.7
      },
      "risk_level": "High",
      "analysis": {
        "gfw_loss": {
          "total_loss_area_ha": 2.34,
          "loss_percentage": 14.9,
          "has_loss": true
        },
        "jrc_loss": {
          "total_loss_area_ha": 1.89,
          "loss_percentage": 12.0,
          "has_loss": true
        },
        "sbtn_loss": {
          "total_loss_area_ha": 0.75,
          "loss_percentage": 4.8,
          "has_loss": true
        }
      },
      "account_used": "eudr-3.json",
      "processing_time_seconds": 2.1
    }
  ]
}
```

## 🔍 Penjelasan Data

### 20 Plot yang Disertakan:
1. **Central African Republic** - Forestry Concession (15.7 ha)
2. **Ivory Coast** - Cocoa Plantation Yamoussoukro (28.3 ha)
3. **Brazil** - Amazon Forest Reserve (45.8 ha)
4. **Ghana** - Cocoa Estate Ashanti (22.1 ha)
5. **Indonesia** - Palm Oil Plantation Riau (35.6 ha)
6. **Indonesia** - Rubber Estate Sumatra (18.9 ha)
7. **Indonesia** - Coffee Plantation Java (27.4 ha)
8. **Ivory Coast** - Palm Oil Farm Abidjan (31.2 ha)
9. **Nigeria** - Cocoa Farm Cross River (24.8 ha)
10. **China** - Forest Plantation Guangxi (19.3 ha)
11. **China** - Rubber Estate Hainan (33.7 ha)
12. **China** - Tea Plantation Yunnan (16.8 ha)
13. **Ghana** - Palm Oil Plantation Greater Accra (29.5 ha)
14. **Nigeria** - Rubber Farm Rivers State (26.2 ha)
15. **Brazil** - Soybean Farm Mato Grosso (41.9 ha)
16. **Indonesia** - Cocoa Plantation Sulawesi (20.3 ha)
17. **Nigeria** - Coffee Estate Plateau (15.4 ha)
18. **Ivory Coast** - Rubber Estate Bouake (37.6 ha)
19. **Ghana** - Coffee Farm Western Region (14.7 ha)
20. **China** - Rice Plantation Guangdong (23.1 ha)

## 🎯 Testing dengan cURL

```bash
curl -X POST "http://localhost:8000/api/v1/process-geojson" \
  -H "Content-Type: application/json" \
  -d @example_geojson_20_plots.json
```

**Catatan**: Untuk cURL, Anda perlu wrap GeoJSON dalam format:
```json
{"geojson": {...isi dari example_geojson_20_plots.json...}}
```

## 🔧 Troubleshooting

### Error 422: Unprocessable Entity
- **Penyebab**: Menggunakan endpoint yang salah atau format request salah
- **Solusi**: Gunakan `/api/v1/process-geojson` dengan format `{"geojson": {...}}`

### Error 500: Internal Server Error
- **Penyebab**: Service accounts tidak tersedia atau Earth Engine error
- **Solusi**: Pastikan 16 service account files ada di folder `authentication/`

### Connection Error
- **Penyebab**: API server tidak running
- **Solusi**: Start server dengan `python app.py`

## ✅ Validasi Hasil

Script akan otomatis menampilkan:
- Total features yang diproses
- Jumlah plot High Risk vs Low Risk
- Service accounts yang digunakan
- Waktu processing
- Sample hasil untuk 3 plot pertama

---

**Happy Testing! 🎉**
