"""
Sustainit API Results - Excel Template Generator
Generates Excel templates for all Sustainit API endpoints results

Usage:
    python sustainit_results_template.py
    
Output:
    - sustainit_protected_area_results.xlsx
    - sustainit_deforestation_results.xlsx
    - sustainit_geometry_validation_results.xlsx
    - sustainit_rainfall_results.xlsx
    - sustainit_ghg_emission_results.xlsx
    - sustainit_comprehensive_report.xlsx
"""

import pandas as pd
from datetime import datetime
import os

# Set output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def create_protected_area_template():
    """Create Protected Area Analysis Results Template"""
    
    # Summary sheet
    summary_data = {
        'Metric': [
            'File Name',
            'File Size (MB)',
            'Total Features',
            'Total Processed',
            'Compliant',
            'Indicative',
            'Non-Compliant',
            'Errors',
            'Processing Time (seconds)',
            'Analysis Date',
            'Dataset Used'
        ],
        'Value': [
            'plots.geojson',
            2.5,
            100,
            100,
            85,
            10,
            5,
            0,
            45.2,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'WCMC/WDPA/current/polygons'
        ],
        'Percentage': [
            '',
            '',
            '',
            '100%',
            '85%',
            '10%',
            '5%',
            '0%',
            '',
            '',
            ''
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Feature details sheet
    features_data = {
        'Feature ID': ['Plot-001', 'Plot-002', 'Plot-003', 'Plot-004', 'Plot-005'],
        'WDPA Status': ['Compliant', 'Indicative', 'Non-Compliant', 'Compliant', 'Compliant'],
        'WDPA Categories': ['None', 'V, VI', 'Ia, II', 'None', 'None'],
        'Area (hectares)': [25.5, 18.3, 12.7, 30.2, 22.8],
        'Analysis Timestamp': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')] * 5,
        'Latitude': [-2.5234, -2.5456, -2.5678, -2.5890, -2.6012],
        'Longitude': [110.1234, 110.1456, 110.1678, 110.1890, 110.2012],
        'Compliance Score': ['Pass', 'Review', 'Fail', 'Pass', 'Pass']
    }
    features_df = pd.DataFrame(features_data)
    
    # IUCN Categories reference sheet
    iucn_data = {
        'Category': ['Ia', 'Ib', 'II', 'III', 'IV', 'V', 'VI'],
        'Description': [
            'Strict Nature Reserve',
            'Wilderness Area',
            'National Park',
            'Natural Monument',
            'Habitat/Species Management Area',
            'Protected Landscape/Seascape',
            'Managed Resource Protected Area'
        ],
        'Status': [
            'Non-Compliant',
            'Non-Compliant',
            'Non-Compliant',
            'Non-Compliant',
            'Non-Compliant',
            'Indicative',
            'Indicative'
        ]
    }
    iucn_df = pd.DataFrame(iucn_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_protected_area_results.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        features_df.to_excel(writer, sheet_name='Feature Details', index=False)
        iucn_df.to_excel(writer, sheet_name='IUCN Categories', index=False)
    
    print(f"✅ Created: {output_file}")


def create_deforestation_template():
    """Create Deforestation Analysis Results Template"""
    
    # Summary sheet
    summary_data = {
        'Metric': [
            'File Name',
            'File Size (MB)',
            'Total Features',
            'Total Processed',
            'High Risk',
            'Low Risk',
            'Processing Time (seconds)',
            'Analysis Date',
            'Analysis Period'
        ],
        'Value': [
            'plots.geojson',
            3.2,
            50,
            50,
            8,
            42,
            120.5,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '2021-2024'
        ],
        'Percentage': [
            '',
            '',
            '',
            '100%',
            '16%',
            '84%',
            '',
            '',
            ''
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Dataset comparison sheet
    dataset_data = {
        'Dataset': ['GFW Loss', 'JRC Loss', 'SBTN Loss', 'Overall'],
        'Total Loss Area (ha)': [45.5, 38.2, 41.8, 125.5],
        'Average Loss (%)': [8.2, 6.9, 7.5, 7.5],
        'Features with Loss': [8, 7, 8, 10],
        'Max Loss Area (ha)': [3.2, 2.9, 3.0, 3.2],
        'Resolution': ['30m', '10m', '10m', 'Multi-source']
    }
    dataset_df = pd.DataFrame(dataset_data)
    
    # Feature details sheet
    features_data = {
        'Feature ID': ['Plot-001', 'Plot-002', 'Plot-003', 'Plot-004', 'Plot-005'],
        'GFW Loss Area (ha)': [2.5, 0.0, 3.2, 0.0, 1.8],
        'GFW Loss (%)': [5.2, 0.0, 6.8, 0.0, 3.5],
        'JRC Loss Area (ha)': [1.8, 0.0, 2.9, 0.0, 1.5],
        'JRC Loss (%)': [3.7, 0.0, 6.2, 0.0, 2.9],
        'SBTN Loss Area (ha)': [2.1, 0.0, 3.0, 0.0, 1.6],
        'SBTN Loss (%)': [4.3, 0.0, 6.4, 0.0, 3.1],
        'Risk Level': ['High', 'Low', 'High', 'Low', 'High'],
        'EUDR Compliance': ['Non-Compliant', 'Compliant', 'Non-Compliant', 'Compliant', 'Non-Compliant'],
        'Total Area (ha)': [48.5, 52.3, 46.8, 55.1, 51.2]
    }
    features_df = pd.DataFrame(features_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_deforestation_results.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        dataset_df.to_excel(writer, sheet_name='Dataset Comparison', index=False)
        features_df.to_excel(writer, sheet_name='Feature Details', index=False)
    
    print(f"✅ Created: {output_file}")


def create_geometry_validation_template():
    """Create Geometry Validation Results Template"""
    
    # Summary sheet
    summary_data = {
        'Metric': [
            'File Name',
            'File Size (MB)',
            'Total Features',
            'Valid',
            'Invalid',
            'Errors',
            'Processing Time (seconds)',
            'Analysis Date'
        ],
        'Value': [
            'plots.geojson',
            1.8,
            75,
            68,
            7,
            0,
            3.2,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ],
        'Percentage': [
            '',
            '',
            '',
            '91%',
            '9%',
            '0%',
            '',
            ''
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Issue types sheet
    issues_data = {
        'Issue Type': [
            'Self-Intersection',
            'Duplicate Vertices',
            'Zero Area',
            'Not Ring',
            'Invalid Geometry'
        ],
        'Count': [3, 2, 1, 1, 0],
        'Severity': ['High', 'Medium', 'High', 'Critical', 'Critical'],
        'Description': [
            'Polygon intersects itself',
            'Repeated coordinate points',
            'Polygon with no or minimal area',
            'Unclosed polygon boundary',
            'Malformed geometry structure'
        ]
    }
    issues_df = pd.DataFrame(issues_data)
    
    # Feature details sheet
    features_data = {
        'Feature ID': ['Plot-001', 'Plot-002', 'Plot-003', 'Plot-004', 'Plot-005'],
        'Validation Status': ['Valid', 'Invalid', 'Valid', 'Valid', 'Invalid'],
        'Is Valid': [True, False, True, True, False],
        'Self Intersection': [False, True, False, False, False],
        'Duplicate Vertices': [False, False, False, False, True],
        'Zero Area': [False, False, False, False, False],
        'Not Ring': [False, False, False, False, False],
        'Area (sqm)': [25000.5, 0.0, 18500.2, 32000.8, 15200.3],
        'Issues': ['None', 'Self-intersection detected', 'None', 'None', 'Duplicate vertices found']
    }
    features_df = pd.DataFrame(features_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_geometry_validation_results.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        issues_df.to_excel(writer, sheet_name='Issue Types', index=False)
        features_df.to_excel(writer, sheet_name='Feature Details', index=False)
    
    print(f"✅ Created: {output_file}")


def create_rainfall_template():
    """Create Rainfall Analysis Results Template"""
    
    # Summary sheet
    summary_data = {
        'Metric': [
            'File Name',
            'File Size (MB)',
            'Total Features',
            'Average Rainfall (mm)',
            'Min Rainfall (mm)',
            'Max Rainfall (mm)',
            'Processing Time (seconds)',
            'Analysis Period Start',
            'Analysis Period End',
            'Data Source',
            'Resolution'
        ],
        'Value': [
            'plots.geojson',
            2.1,
            60,
            450.5,
            295.5,
            520.8,
            180.3,
            '2023-10-01',
            '2024-01-31',
            'CHIRPS Daily',
            '100m (downscaled)'
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Distribution sheet
    distribution_data = {
        'Rainfall Range (mm)': ['0-300', '300-400', '400-500', '500+'],
        'Feature Count': [8, 15, 25, 12],
        'Percentage': ['13.3%', '25.0%', '41.7%', '20.0%'],
        'Classification': ['Low', 'Medium-Low', 'Medium-High', 'High']
    }
    distribution_df = pd.DataFrame(distribution_data)
    
    # Feature details sheet
    features_data = {
        'Feature ID': ['Plot-001', 'Plot-002', 'Plot-003', 'Plot-004', 'Plot-005'],
        'Mean Rainfall (mm)': [450.5, 380.2, 520.8, 295.5, 475.3],
        'Min Rainfall (mm)': [420.0, 350.5, 490.2, 270.0, 445.0],
        'Max Rainfall (mm)': [480.0, 410.8, 550.5, 320.5, 505.5],
        'Std Deviation (mm)': [15.3, 18.7, 12.1, 14.2, 16.5],
        'Area (hectares)': [25.5, 18.3, 32.7, 28.1, 24.9],
        'Classification': ['Medium-High', 'Medium-Low', 'High', 'Low', 'Medium-High'],
        'Suitability': ['Good', 'Fair', 'Excellent', 'Poor', 'Good']
    }
    features_df = pd.DataFrame(features_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_rainfall_results.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        distribution_df.to_excel(writer, sheet_name='Distribution', index=False)
        features_df.to_excel(writer, sheet_name='Feature Details', index=False)
    
    print(f"✅ Created: {output_file}")


def create_ghg_emission_template():
    """Create GHG Emission Results Template"""
    
    # Summary sheet
    summary_data = {
        'Metric': [
            'File Name',
            'File Size (MB)',
            'Total Features',
            'High Risk',
            'Low Risk',
            'Total Deforestation Area (ha)',
            'Total Net Emission (tCO2e)',
            'Average Emission Intensity (tCO2e/ha)',
            'Processing Time (seconds)',
            'Analysis Date'
        ],
        'Value': [
            'plots.geojson',
            2.8,
            40,
            12,
            28,
            45.5,
            12450.75,
            273.5,
            240.8,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ],
        'Percentage': [
            '',
            '',
            '',
            '30%',
            '70%',
            '',
            '',
            '',
            '',
            ''
        ]
    }
    summary_df = pd.DataFrame(summary_data)
    
    # Dataset emissions sheet
    dataset_data = {
        'Dataset': ['GFW', 'JRC', 'SBTN', 'Total'],
        'Loss Area (ha)': [18.5, 15.0, 12.0, 45.5],
        'Gross CO2 (tCO2e)': [5180.0, 4200.0, 3360.0, 12740.0],
        'Gross N2O (tCO2e)': [7.5, 6.0, 4.8, 18.3],
        'Gross CH4 (tCO2e)': [5.5, 4.5, 3.6, 13.6],
        'SOC Emission (tCO2e)': [481.0, 390.0, 312.0, 1183.0],
        'Post Carbon Stock (tC)': [-1054.5, -855.0, -684.0, -2593.5],
        'Net Emission (tCO2e)': [5200.5, 4100.25, 3150.0, 12450.75],
        'Emission Intensity (tCO2e/ha)': [281.1, 273.4, 262.5, 273.5]
    }
    dataset_df = pd.DataFrame(dataset_data)
    
    # Emission components sheet
    components_data = {
        'Component': [
            'Gross CO2',
            'Gross N2O',
            'Gross CH4',
            'Total Gross',
            'SOC Emission',
            'Gross with SOC',
            'Post Carbon Stock',
            'Net Emission'
        ],
        'Value (tCO2e)': [
            10800.00,
            15.50,
            12.25,
            10827.75,
            1180.00,
            12007.75,
            -3557.00,
            12450.75
        ],
        'Percentage': [
            '86.7%',
            '0.1%',
            '0.1%',
            '87.0%',
            '9.5%',
            '96.4%',
            '-28.6%',
            '100.0%'
        ]
    }
    components_df = pd.DataFrame(components_data)
    
    # Feature details sheet
    features_data = {
        'Feature ID': ['Plot-001', 'Plot-002', 'Plot-003', 'Plot-004', 'Plot-005'],
        'Forest Type': ['Secondary', 'Primary', 'Secondary', 'Primary', 'Secondary'],
        'GFW Loss (ha)': [2.5, 0.0, 3.2, 0.0, 1.8],
        'GFW Emission (tCO2e)': [623.1, 0.0, 892.5, 0.0, 485.2],
        'JRC Loss (ha)': [1.8, 0.0, 2.9, 0.0, 1.5],
        'JRC Emission (tCO2e)': [485.2, 0.0, 756.3, 0.0, 412.5],
        'SBTN Loss (ha)': [2.1, 0.0, 3.0, 0.0, 1.6],
        'SBTN Emission (tCO2e)': [532.5, 0.0, 821.7, 0.0, 438.8],
        'Total Net Emission (tCO2e)': [1640.8, 0.0, 2470.5, 0.0, 1336.5],
        'Risk Level': ['High', 'Low', 'High', 'Low', 'High']
    }
    features_df = pd.DataFrame(features_data)
    
    # Parameters sheet
    parameters_data = {
        'Parameter': [
            'Forest Biomass - Primary (tCO2e/ha)',
            'Forest Biomass - Secondary (tCO2e/ha)',
            'Burning Efficiency',
            'Combustion Factor',
            'N2O Emission Factor (kg/kg)',
            'CH4 Emission Factor (kg/kg)',
            'N2O GWP',
            'CH4 GWP',
            'SOC Constant (tCO2e/ha)',
            'Post AGB (tC/ha)',
            'Post BGB (tC/ha)'
        ],
        'Value': [
            520.0,
            280.0,
            0.5,
            0.5,
            0.007,
            0.0048,
            298,
            25,
            26.0,
            47.0,
            10.0
        ],
        'Unit': [
            'tCO2e/ha',
            'tCO2e/ha',
            'fraction',
            'fraction',
            'kg/kg',
            'kg/kg',
            'CO2e factor',
            'CO2e factor',
            'tCO2e/ha',
            'tC/ha',
            'tC/ha'
        ],
        'Source': [
            'IPCC Guidelines',
            'IPCC Guidelines',
            'IPCC Guidelines',
            'IPCC Guidelines',
            'IPCC Guidelines',
            'IPCC Guidelines',
            'IPCC AR5',
            'IPCC AR5',
            'Database',
            'IPCC Guidelines',
            'IPCC Guidelines'
        ]
    }
    parameters_df = pd.DataFrame(parameters_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_ghg_emission_results.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        dataset_df.to_excel(writer, sheet_name='Dataset Emissions', index=False)
        components_df.to_excel(writer, sheet_name='Emission Components', index=False)
        features_df.to_excel(writer, sheet_name='Feature Details', index=False)
        parameters_df.to_excel(writer, sheet_name='Parameters', index=False)
    
    print(f"✅ Created: {output_file}")


def create_comprehensive_report():
    """Create Comprehensive Multi-Endpoint Report"""
    
    # Project overview sheet
    overview_data = {
        'Metric': [
            'Project Name',
            'Total Features Analyzed',
            'Total Area (hectares)',
            'Analysis Date',
            'Project Location',
            'Commodity Type',
            'Analysis Period',
            'API Version'
        ],
        'Value': [
            'Palm Oil Plantation Compliance',
            100,
            2500,
            datetime.now().strftime('%Y-%m-%d'),
            'Indonesia - Kalimantan',
            'Palm Oil',
            '2021-2024',
            'v2.1.0'
        ]
    }
    overview_df = pd.DataFrame(overview_data)
    
    # Compliance scorecard sheet
    scorecard_data = {
        'Category': [
            'Protected Area Compliance',
            'Deforestation Risk',
            'Geometry Quality',
            'Environmental Data',
            'Carbon Impact',
            'OVERALL SCORE'
        ],
        'Score': [78, 84, 91, 85, 70, 82],
        'Max Score': [100, 100, 100, 100, 100, 100],
        'Rating': ['Good', 'Good', 'Excellent', 'Good', 'Fair', 'Good'],
        'Status': ['Pass', 'Pass', 'Pass', 'Pass', 'Review', 'Pass']
    }
    scorecard_df = pd.DataFrame(scorecard_data)
    
    # Multi-endpoint summary sheet
    multi_summary_data = {
        'Endpoint': [
            'Protected Area',
            'Deforestation',
            'Geometry Validation',
            'Rainfall',
            'GHG Emission'
        ],
        'Features Processed': [100, 50, 75, 60, 40],
        'Pass/Valid Count': [85, 42, 68, 60, 28],
        'Fail/Invalid Count': [5, 8, 7, 0, 12],
        'Warning Count': [10, 0, 0, 0, 0],
        'Success Rate (%)': [85.0, 84.0, 91.0, 100.0, 70.0],
        'Processing Time (s)': [45.2, 120.5, 3.2, 180.3, 240.8],
        'Status': ['Pass', 'Pass', 'Pass', 'Pass', 'Review']
    }
    multi_summary_df = pd.DataFrame(multi_summary_data)
    
    # Risk matrix sheet
    risk_matrix_data = {
        'Risk Level': ['Low', 'Medium', 'High', 'Critical'],
        'Feature Count': [72, 18, 10, 0],
        'Percentage': ['72%', '18%', '10%', '0%'],
        'Description': [
            'All compliance criteria met',
            'Minor issues requiring monitoring',
            'Significant issues requiring action',
            'Immediate intervention required'
        ],
        'Action Required': [
            'Continue monitoring',
            'Enhanced monitoring',
            'Remediation plan',
            'Immediate suspension'
        ]
    }
    risk_matrix_df = pd.DataFrame(risk_matrix_data)
    
    # Key findings sheet
    findings_data = {
        'Category': [
            'Protected Areas',
            'Protected Areas',
            'Deforestation',
            'Deforestation',
            'Geometry',
            'Rainfall',
            'GHG Emissions',
            'GHG Emissions'
        ],
        'Finding': [
            '5% of features in strict protected areas (Non-compliant)',
            '10% in sustainable use zones (Requires review)',
            '16% of features show forest loss 2021-2024',
            'Average loss of 2.5 ha per affected feature',
            '9% of features have geometry issues',
            'Rainfall adequate for cultivation (450mm avg)',
            'Total emissions: 12,450 tCO2e',
            'High emission features linked to deforestation'
        ],
        'Severity': [
            'High',
            'Medium',
            'High',
            'Medium',
            'Medium',
            'Low',
            'Medium',
            'High'
        ],
        'Recommendation': [
            'Immediate investigation required',
            'Obtain documentation for sustainable use',
            'Verify land use change authorization',
            'Implement restoration program',
            'Fix geometry issues before submission',
            'Continue current water management',
            'Implement carbon offset program',
            'Prioritize high-emission areas for action'
        ]
    }
    findings_df = pd.DataFrame(findings_data)
    
    # Write to Excel
    output_file = os.path.join(OUTPUT_DIR, 'sustainit_comprehensive_report.xlsx')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        overview_df.to_excel(writer, sheet_name='Project Overview', index=False)
        scorecard_df.to_excel(writer, sheet_name='Compliance Scorecard', index=False)
        multi_summary_df.to_excel(writer, sheet_name='Multi-Endpoint Summary', index=False)
        risk_matrix_df.to_excel(writer, sheet_name='Risk Matrix', index=False)
        findings_df.to_excel(writer, sheet_name='Key Findings', index=False)
    
    print(f"✅ Created: {output_file}")


def main():
    """Generate all Excel templates"""
    print("🔄 Generating Sustainit API Results Excel Templates...\n")
    
    create_protected_area_template()
    create_deforestation_template()
    create_geometry_validation_template()
    create_rainfall_template()
    create_ghg_emission_template()
    create_comprehensive_report()
    
    print(f"\n✅ All templates created successfully!")
    print(f"📁 Output directory: {OUTPUT_DIR}")
    print(f"\n📋 Generated files:")
    print("   1. sustainit_protected_area_results.xlsx")
    print("   2. sustainit_deforestation_results.xlsx")
    print("   3. sustainit_geometry_validation_results.xlsx")
    print("   4. sustainit_rainfall_results.xlsx")
    print("   5. sustainit_ghg_emission_results.xlsx")
    print("   6. sustainit_comprehensive_report.xlsx")
    print(f"\n💡 Usage: Open Excel files and replace sample data with actual API responses")


if __name__ == "__main__":
    main()
