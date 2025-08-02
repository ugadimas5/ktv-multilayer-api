"""
Contoh penggunaan API EUDR dengan 20 data GeoJSON
Script ini menunjukkan cara yang benar untuk menggunakan endpoint /api/v1/process-geojson
dengan parallel processing menggunakan 16 service accounts.
"""

import requests
import json
import time
from datetime import datetime

# Konfigurasi API
API_BASE_URL = "http://localhost:8000"
GEOJSON_ENDPOINT = "/api/v1/process-geojson"

def load_geojson_data():
    """Load contoh GeoJSON dari file"""
    with open('example_geojson_20_plots.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def send_bulk_geojson_request():
    """
    Kirim bulk GeoJSON request ke API dengan format yang benar
    Endpoint: /api/v1/process-geojson
    Method: POST
    Body: {"geojson": {...}}
    """
    
    print("🚀 Starting EUDR Bulk Analysis with 20 Plots")
    print("=" * 60)
    
    # Load GeoJSON data
    geojson_data = load_geojson_data()
    print(f"📊 Loaded {len(geojson_data['features'])} features from GeoJSON")
    
    # Prepare request payload - FORMAT YANG BENAR!
    payload = {
        "geojson": geojson_data  # GeoJSON harus di dalam key "geojson"
    }
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print(f"🌐 Sending request to: {API_BASE_URL}{GEOJSON_ENDPOINT}")
    print(f"📦 Request size: {len(json.dumps(payload))} characters")
    print("⏱️  Starting parallel processing...")
    
    start_time = time.time()
    
    try:
        # Send POST request
        response = requests.post(
            url=f"{API_BASE_URL}{GEOJSON_ENDPOINT}",
            json=payload,
            headers=headers,
            timeout=300  # 5 minutes timeout
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"⏱️  Processing completed in: {processing_time:.2f} seconds")
        print(f"📡 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS! Bulk processing completed")
            print("=" * 60)
            
            # Analisis hasil
            print(f"📈 Results Summary:")
            print(f"   Total features processed: {len(result.get('results', []))}")
            
            # Hitung risk distribution
            high_risk_count = 0
            low_risk_count = 0
            
            for feature_result in result.get('results', []):
                if feature_result.get('risk_level') == 'High':
                    high_risk_count += 1
                else:
                    low_risk_count += 1
            
            print(f"   🔴 High risk plots: {high_risk_count}")
            print(f"   🟢 Low risk plots: {low_risk_count}")
            print(f"   ⚡ Parallel processing: {result.get('parallel_processing_enabled', False)}")
            print(f"   👥 Service accounts used: {result.get('accounts_used', 'N/A')}")
            print(f"   ⏱️  Processing time: {result.get('processing_time_seconds', processing_time):.2f}s")
            
            # Tampilkan beberapa contoh hasil
            print("\n📋 Sample Results (first 3 plots):")
            for i, feature_result in enumerate(result.get('results', [])[:3]):
                plot_info = feature_result.get('input_properties', {})
                print(f"   Plot {i+1}: {plot_info.get('plot_id', 'Unknown')} - "
                      f"{plot_info.get('country_name', 'Unknown')} - "
                      f"Risk: {feature_result.get('risk_level', 'Unknown')}")
            
            return result
            
        else:
            print(f"❌ ERROR! Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 5 minutes")
        return None
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error - pastikan API server sudah running")
        return None
    except Exception as e:
        print(f"💥 Unexpected error: {str(e)}")
        return None

def main():
    """Main function"""
    print("🌍 KTV EUDR Multilayer API - Bulk GeoJSON Processing Test")
    print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Info tentang parallel processing
    print("🔧 Configuration:")
    print("   • Endpoint: /api/v1/process-geojson")
    print("   • Parallel Processing: Enabled (16 service accounts)")
    print("   • Max Workers: 8 concurrent threads")
    print("   • Round-robin account distribution")
    print()
    
    # Execute bulk request
    result = send_bulk_geojson_request()
    
    if result:
        print("\n💾 Want to save results? Uncomment the following code:")
        print("# with open('eudr_results.json', 'w', encoding='utf-8') as f:")
        print("#     json.dump(result, f, indent=2, ensure_ascii=False)")
    
    print("\n✨ Test completed!")

if __name__ == "__main__":
    main()
