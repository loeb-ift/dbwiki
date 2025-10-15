import pandas as pd
import random
import string
import os
from datetime import datetime, timedelta

# --- Configuration ---
NUM_PRODUCTS = 1000
OUTPUT_DIR = 'mock_training_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Rule Definitions ---

def generate_electronics_pn(index):
    """Generates part number like E-2023-000123"""
    year = datetime.now().year
    return f"E-{year}-{index:06d}"

def generate_mechanical_pn():
    """Generates part number like MEC-10023456"""
    department = random.choice(['MEC', 'CNC', 'ASM'])
    number = random.randint(10000000, 99999999)
    return f"{department}-{number}"

def generate_software_pn():
    """Generates part number like SW-CS60-A1-XDE45"""
    product_code = random.choice(['CS60', 'VS22', 'PH10'])
    version = f"V{random.randint(1, 5)}"
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"SW-{product_code}-{version}-{random_part}"

# --- Data Generation ---

products_data = []
inventory_data = []
shipments_data = []

for i in range(1, NUM_PRODUCTS + 1):
    category = random.choices(['Electronics', 'Mechanical', 'Software'], weights=[0.5, 0.3, 0.2], k=1)[0]
    
    if category == 'Electronics':
        part_number = generate_electronics_pn(i)
        product_name = f"Resistor Pack {i}"
    elif category == 'Mechanical':
        part_number = generate_mechanical_pn()
        product_name = f"Mounting Bracket {i}"
    else: # Software
        part_number = generate_software_pn()
        product_name = f"License Key {i}"
        
    products_data.append({
        "product_id": i,
        "part_number": part_number,
        "product_name": product_name,
        "category": category
    })
    
    # Generate corresponding inventory and shipment data
    if random.random() > 0.1: # 90% of products have inventory
        inventory_data.append({
            "inventory_id": i,
            "part_number": part_number,
            "quantity": random.randint(0, 500),
            "location": f"A{random.randint(1, 10)}-{random.randint(1, 5)}"
        })
        
    if random.random() > 0.4: # 60% of products have shipments
        num_shipments = random.randint(1, 5)
        for j in range(num_shipments):
            shipment_date = datetime.now() - timedelta(days=random.randint(0, 365))
            shipments_data.append({
                "shipment_id": len(shipments_data) + 1,
                "part_number": part_number,
                "shipped_quantity": random.randint(1, 20),
                "shipment_date": shipment_date.strftime('%Y-%m-%d')
            })

# --- Create DataFrames and Export ---

df_products = pd.DataFrame(products_data)
df_inventory = pd.DataFrame(inventory_data)
df_shipments = pd.DataFrame(shipments_data)

products_path = os.path.join(OUTPUT_DIR, 'products.csv')
inventory_path = os.path.join(OUTPUT_DIR, 'inventory.csv')
shipments_path = os.path.join(OUTPUT_DIR, 'shipments.csv')

df_products.to_csv(products_path, index=False)
df_inventory.to_csv(inventory_path, index=False)
df_shipments.to_csv(shipments_path, index=False)

print(f"Successfully generated {len(df_products)} products, {len(df_inventory)} inventory records, and {len(df_shipments)} shipment records.")
print(f"CSV files are saved in the '{OUTPUT_DIR}' directory.")