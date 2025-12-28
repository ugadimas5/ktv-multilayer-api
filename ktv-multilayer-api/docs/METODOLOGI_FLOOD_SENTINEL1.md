# Metodologi Detail Pembuatan Layer Flood dari Sentinel-1

## 1. Sumber Data
- **Satelit**: Sentinel-1 (C-band Synthetic Aperture Radar)
- **Produk**: Sentinel-1 GRD (Ground Range Detected)
- **Resolusi**: ~10 meter
- **Polarisasi**: VV (Vertical transmit, Vertical receive)
- **Periode Analisis**: 2021–2025 (bisa disesuaikan)

## 2. Proses Pengolahan Data

### a. Seleksi Citra Musiman
- **Musim Basah**: Desember (12-01 s/d 12-31)
- **Musim Kering**: Agustus (08-01 s/d 08-31)
- Untuk setiap tahun, ambil citra Sentinel-1 pada dua periode tersebut.

### b. Preprocessing
- **Filter Area**: Citra difilter pada area of interest (Indonesia atau geometry user).
- **Polarization**: Pilih band 'VV' saja.
- **Speckle Filtering**: Terapkan focal mean 50 meter untuk mengurangi noise speckle.
- **Composite**: Ambil nilai minimum (10th percentile) dari stack citra pada masing-masing musim.

### c. Deteksi Air
- **Threshold**: Piksel dengan nilai VV < -15 dB dianggap sebagai air.
- **Output**: Binary mask (1 = air, 0 = bukan air) untuk masing-masing musim.

### d. Deteksi Banjir Sementara
- **Definisi Banjir**: Piksel yang terdeteksi air pada musim basah, tetapi kering pada musim kering.
- **Rumus**: `Flood = (Water_wet == 1) AND (Water_dry == 0)`
- **Output**: Layer banjir tahunan (1 = banjir, 0 = tidak banjir)

### e. Indeks Hazard Banjir (Flood Hazard Index)
- **Kalkulasi**: Jumlah tahun piksel mengalami banjir dibagi total tahun analisis.
- **Rumus**: `Flood_Hazard_Index = (Sum(Flood_years)) / (Total_years)`
- **Output**: Layer kontinu 0–1 (0 = tidak pernah banjir, 1 = selalu banjir)

### f. Deteksi Air Permanen
- **Definisi**: Piksel yang selalu terdeteksi air pada semua musim dan tahun.
- **Rumus**: `Permanent_Water = (Water_wet == 1) AND (Water_dry == 1) untuk semua tahun`
- **Output**: Layer binary air permanen

## 3. Visualisasi
- **Flood Hazard Index**: Skala warna dari putih (0) ke merah (1)
- **Permanent Water**: Biru
- **Flood Year**: Cyan

## 4. Catatan Teknis
- **Cloud Masking**: Tidak diperlukan (radar tidak terpengaruh awan)
- **Vegetasi**: Area dengan vegetasi rapat bisa mengurangi sensitivitas deteksi air/banjir.
- **Urban Area**: Refleksi bangunan bisa menyebabkan false positive.
- **Threshold**: Nilai -15 dB dapat disesuaikan untuk sensitivitas lokal.

## 5. Referensi
- [Sentinel-1 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar)
- [Earth Engine Sentinel-1 Documentation](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)
- [Peer-reviewed: Pekel et al. (2016), High-resolution mapping of global surface water and its long-term changes, Nature]

---

Dokumentasi ini menjelaskan secara detail tahapan pembuatan layer banjir berbasis radar Sentinel-1 yang digunakan pada API multilayer.
