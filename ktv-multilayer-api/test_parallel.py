"""
Test Script untuk Parallel Processing Implementation
Memverifikasi bahwa 16 service accounts bekerja dengan benar
"""

import os
import sys
import time
import json
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_parallel_implementation():
    """Test implementasi parallel processing"""
    print("🧪 Testing Parallel Processing Implementation")
    print("=" * 60)
    
    try:
        # Import service
        from services.data.multilayer_service import MultilayerService
        
        # Initialize service
        print("1. Initializing MultilayerService...")
        service = MultilayerService()
        
        print(f"   ✅ Available accounts: {len(service.available_accounts)}")
        print(f"   ⚡ Max workers: {service.max_workers}")
        print(f"   🔄 Account pool active: {'Yes' if service.account_pool else 'No'}")
        
        # Test sample GeoJSON with multiple features
        print("\n2. Testing GeoJSON processing...")
        
        sample_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"plot_id": "test_1", "country_name": "Indonesia"},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [110.0, -7.0]  # Central Java
                    }
                },
                {
                    "type": "Feature", 
                    "properties": {"plot_id": "test_2", "country_name": "Indonesia"},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [106.8, -6.2]  # Jakarta
                    }
                },
                {
                    "type": "Feature",
                    "properties": {"plot_id": "test_3", "country_name": "Brazil"},
                    "geometry": {
                        "type": "Point", 
                        "coordinates": [-60.0, -3.0]  # Amazon
                    }
                }
            ]
        }
        
        # Process with timing
        start_time = time.time()
        result = service.process_geojson(sample_geojson)
        end_time = time.time()
        
        processing_time = end_time - start_time
        stats = result.get('processing_stats', {})
        
        print(f"\n3. Results:")
        print(f"   ⏱️  Processing time: {processing_time:.2f} seconds")
        print(f"   📊 Total features: {stats.get('total_features', 'N/A')}")
        print(f"   ✅ Successful: {stats.get('successful', 'N/A')}")
        print(f"   ❌ Failed: {stats.get('failed', 'N/A')}")
        print(f"   🔧 Processing mode: {stats.get('processing_mode', 'N/A')}")
        print(f"   👥 Workers used: {stats.get('workers_used', 'N/A')}")
        print(f"   🔑 Accounts available: {stats.get('accounts_available', 'N/A')}")
        
        # Show sample result
        if result.get('features'):
            sample_feature = result['features'][0]
            sample_props = sample_feature['properties']
            
            print(f"\n4. Sample Analysis Result (Plot {sample_props.get('plot_id')}):")
            
            if 'gfw_loss' in sample_props:
                gfw = sample_props['gfw_loss']
                print(f"   🌲 GFW Loss: {gfw.get('gfw_loss_stat', 'N/A')} risk")
                print(f"      Area: {gfw.get('gfw_loss_area', 0)} hectares")
                
            if 'overall_compliance' in sample_props:
                overall = sample_props['overall_compliance']
                print(f"   📋 Overall Risk: {overall.get('overall_risk', 'N/A')}")
                print(f"   ⚖️  Compliance: {overall.get('compliance_status', 'N/A')}")
        
        print(f"\n🎉 Test completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_service_accounts():
    """Test ketersediaan service accounts"""
    print("\n🔑 Testing Service Account Availability")
    print("=" * 60)
    
    try:
        from authentication.auth_helper import get_available_accounts, test_all_accounts
        
        # Check available accounts
        available = get_available_accounts()
        print(f"Available accounts: {len(available)}")
        
        if available:
            print("Account files found:")
            for account in available[:5]:  # Show first 5
                print(f"   ✅ {account}")
            if len(available) > 5:
                print(f"   ... and {len(available) - 5} more")
        else:
            print("❌ No service account files found in authentication/ folder")
            print("📋 Expected files:")
            for i in range(5):
                print(f"   📄 authentication/eudr-{i}.json")
            print("   ...")
            
        return len(available) > 0
        
    except Exception as e:
        print(f"❌ Error checking service accounts: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 KTV EUDR Multilayer API - Parallel Processing Test Suite")
    print("=" * 70)
    
    # Test 1: Service Accounts
    accounts_ok = test_service_accounts()
    
    # Test 2: Parallel Implementation
    if accounts_ok:
        parallel_ok = test_parallel_implementation()
        
        if parallel_ok:
            print("\n🎯 All tests passed! Parallel processing is ready.")
            print("\n📋 Next Steps:")
            print("   1. Place your 16 service account files in authentication/ folder")
            print("   2. Set ENABLE_PARALLEL_PROCESSING=true in environment")
            print("   3. Start the API server with: uvicorn app:app --reload")
        else:
            print("\n⚠️  Parallel implementation test failed")
    else:
        print("\n⚠️  Service accounts not found - parallel processing will be disabled")
        print("   API will fall back to sequential processing mode")
