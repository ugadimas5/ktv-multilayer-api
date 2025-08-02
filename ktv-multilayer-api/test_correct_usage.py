#!/usr/bin/env python3
"""
Test script untuk menggunakan endpoint yang benar dengan parallel processing
Menunjukkan cara menggunakan /api/v1/process-geojson dengan data GeoJSON Anda
"""

import requests
import json

# Your GeoJSON data (sample from your error)
geojson_data = {
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
                "coordinates": [[
                    [16.2800016976857, 4.14723820524654],
                    [16.2798367678978, 4.14695536937449],
                    [16.2810703578022, 4.14705657022182],
                    [16.2800016976857, 4.14723820524654]
                ]]
            }
        },
        {
            "type": "Feature",
            "properties": {
                "plot_id": "PLOT_002", 
                "country_name": "Ivory Coast",
                "farm_name": "Cocoa Plantation Yamoussoukro",
                "area_ha": 28.3
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [2.150806993589529, 7.039736246748737],
                    [2.153811067686209, 7.041439916513774],
                    [2.157072633848318, 7.042206565866722],
                    [2.150806993589529, 7.039736246748737]
                ]]
            }
        }
    ]
}

def test_correct_endpoint():
    """Test dengan endpoint yang benar untuk GeoJSON parallel processing"""
    
    # API endpoint yang BENAR untuk GeoJSON
    url = "http://localhost:8000/api/v1/process-geojson"
    
    # Request body yang BENAR
    payload = {
        "geojson": geojson_data
    }
    
    print("🚀 Testing Correct GeoJSON Endpoint with Parallel Processing")
    print("=" * 60)
    print(f"📡 URL: {url}")
    print(f"📊 Features: {len(geojson_data['features'])}")
    print()
    
    try:
        # Send request
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            
            # Display results
            print("✅ SUCCESS - Parallel processing completed!")
            print()
            
            # Show processing stats
            if 'data' in result and 'processing_stats' in result['data']:
                stats = result['data']['processing_stats']
                print("📈 Processing Statistics:")
                print(f"   🔧 Mode: {stats.get('processing_mode', 'unknown')}")
                print(f"   👥 Workers: {stats.get('workers_used', 'unknown')}")
                print(f"   🔑 Accounts: {stats.get('accounts_available', 'unknown')}")
                print(f"   ✅ Successful: {stats.get('successful', 'unknown')}")
                print(f"   ❌ Failed: {stats.get('failed', 'unknown')}")
                print()
            
            # Show sample results
            if 'data' in result and 'features' in result['data']:
                features = result['data']['features']
                if features:
                    sample = features[0]['properties']
                    plot_id = sample.get('plot_id', 'unknown')
                    
                    print(f"🌲 Sample Result (Plot {plot_id}):")
                    
                    if 'gfw_loss' in sample:
                        gfw = sample['gfw_loss']
                        print(f"   GFW Loss: {gfw.get('gfw_loss_stat', 'N/A')} risk")
                        print(f"   Loss area: {gfw.get('gfw_loss_area', 0)} hectares")
                    
                    if 'overall_compliance' in sample:
                        overall = sample['overall_compliance']
                        print(f"   Overall: {overall.get('overall_risk', 'N/A')} risk")
                        print(f"   Status: {overall.get('compliance_status', 'N/A')}")
            
        else:
            print(f"❌ ERROR - Status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ CONNECTION ERROR: {e}")

def test_single_point_endpoint():
    """Test single point analysis endpoint"""
    
    url = "http://localhost:8000/api/v1/eudr-compliance"
    
    payload = {
        "coordinates": {
            "latitude": 4.14723820524654,
            "longitude": 16.2800016976857
        },
        "buffer_km": 5.0
    }
    
    print("\n🎯 Testing Single Point Analysis")
    print("=" * 60)
    print(f"📡 URL: {url}")
    print(f"📍 Location: {payload['coordinates']['latitude']}, {payload['coordinates']['longitude']}")
    print()
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS - Single point analysis completed!")
            
            if 'data' in result:
                data = result['data']
                print(f"🌲 Results for {data.get('plot_id', 'unknown')}:")
                
                if 'gfw_loss' in data:
                    gfw = data['gfw_loss']
                    print(f"   GFW: {gfw.get('gfw_loss_stat', 'N/A')} risk")
                
                if 'overall_compliance' in data:
                    overall = data['overall_compliance']
                    print(f"   Overall: {overall.get('overall_risk', 'N/A')} risk")
                    
        else:
            print(f"❌ ERROR - Status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ CONNECTION ERROR: {e}")

if __name__ == "__main__":
    print("🧪 KTV EUDR API - Correct Usage Examples")
    print("=" * 70)
    
    # Test bulk GeoJSON processing (with parallel processing)
    test_correct_endpoint()
    
    # Test single point analysis
    test_single_point_endpoint()
    
    print("\n" + "=" * 70)
    print("📋 Summary:")
    print("   ✅ Use /api/v1/process-geojson for bulk GeoJSON (parallel processing)")
    print("   ✅ Use /api/v1/eudr-compliance for single point analysis")
    print("   ❌ Don't use /api/v1/forest-analysis for GeoJSON (it needs coordinates+dates)")
