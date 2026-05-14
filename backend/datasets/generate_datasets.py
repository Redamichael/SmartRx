"""
SmartRx AI — Realistic Ethiopian Dataset Generator
Generates: pharmacies, medicines (with Amharic names), inventory,
           transactions (18 months), patients, prescriptions
"""

import json
import csv
import random
import math
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent

# ─────────────────────────────────────────────
# 1. PHARMACIES  (20 across Addis Ababa + 5 regional)
# ─────────────────────────────────────────────
PHARMACIES = [
    # id, name, amharic_name, sub_city, woreda, lat, lon, type, phone, open_24h
    (1,  "Bole Kenema Pharmacy",       "ቦሌ ቀነማ ፋርማሲ",         "Bole",       "03", 8.9806, 38.7578, "private",    "+251911234501", True),
    (2,  "Piassa Medhanealem Pharmacy","ፒያሳ መድሃኒዓለም ፋርማሲ",  "Addis Ketema","07", 9.0298, 38.7468, "private",    "+251911234502", False),
    (3,  "Megenagna Betezata Pharmacy","መገናኛ ቤተዛታ ፋርማሲ",    "Yeka",       "09", 9.0228, 38.8020, "private",    "+251911234503", True),
    (4,  "CMC Selam Pharmacy",         "ሲኤምሲ ሰላም ፋርማሲ",      "Yeka",       "11", 9.0358, 38.8140, "private",    "+251911234504", False),
    (5,  "Kazanchis Abyssinia Pharmacy","ካዛንቺስ አቢሲኒያ ፋርማሲ", "Kirkos",     "08", 9.0156, 38.7673, "private",    "+251911234505", False),
    (6,  "Mexico Tsenat Pharmacy",     "ሜክሲኮ ጤናት ፋርማሲ",      "Kirkos",     "10", 9.0089, 38.7530, "private",    "+251911234506", True),
    (7,  "Merkato Genet Pharmacy",     "መርካቶ ገነት ፋርማሲ",      "Addis Ketema","01", 9.0356, 38.7298, "private",    "+251911234507", False),
    (8,  "Gerji Tsion Pharmacy",       "ገርጂ ጽዮን ፋርማሲ",       "Bole",       "06", 8.9956, 38.8230, "private",    "+251911234508", False),
    (9,  "Jemo Hayat Pharmacy",        "ጀሞ ሃያት ፋርማሲ",        "Nifas Silk", "02", 8.9612, 38.7190, "private",    "+251911234509", True),
    (10, "Saris Alem Pharmacy",        "ሳሪስ ዓለም ፋርማሲ",       "Nifas Silk", "04", 8.9723, 38.7380, "private",    "+251911234510", False),
    (11, "Lideta Wubet Pharmacy",      "ልደታ ውበት ፋርማሲ",      "Lideta",     "06", 9.0156, 38.7398, "private",    "+251911234511", False),
    (12, "Kolfe Birhan Pharmacy",      "ቆልፌ ብርሃን ፋርማሲ",     "Kolfe",      "03", 9.0289, 38.6998, "private",    "+251911234512", False),
    (13, "Akaki Zion Pharmacy",        "አቃቂ ጽዮን ፋርማሲ",       "Akaki",      "05", 8.8923, 38.7980, "private",    "+251911234513", False),
    (14, "Gulele Hiwot Pharmacy",      "ጉለሌ ሕይወት ፋርማሲ",     "Gulele",     "04", 9.0523, 38.7398, "private",    "+251911234514", False),
    (15, "Arada Tsehay Pharmacy",      "አራዳ ፀሐይ ፋርማሲ",      "Arada",      "10", 9.0389, 38.7523, "government", "+251911234515", False),
    (16, "Yeka Mikael Pharmacy",       "የካ ሚካኤል ፋርማሲ",       "Yeka",       "13", 9.0456, 38.8298, "private",    "+251911234516", False),
    (17, "Nifas Silk Hope Pharmacy",   "ንፋስ ስልክ ተስፋ ፋርማሲ",  "Nifas Silk", "07", 8.9789, 38.7789, "private",    "+251911234517", False),
    (18, "Kirkos Selassie Pharmacy",   "ቅርቆስ ሥላሴ ፋርማሲ",     "Kirkos",     "05", 9.0023, 38.7623, "private",    "+251911234518", False),
    (19, "Bole Atlas Pharmacy",        "ቦሌ አትላስ ፋርማሲ",       "Bole",       "05", 9.0023, 38.7789, "private",    "+251911234519", True),
    (20, "Sarbet Medhanit Pharmacy",   "ሳርቤት መድሃኒት ፋርማሲ",   "Bole",       "08", 8.9878, 38.7623, "private",    "+251911234520", False),
    # Regional
    (21, "Hawassa Rift Pharmacy",      "ሀዋሳ ሪፍት ፋርማሲ",       "Hawassa",    "01", 7.0594, 38.4768, "private",    "+251911234521", False),
    (22, "Bahir Dar Tana Pharmacy",    "ባህር ዳር ጣና ፋርማሲ",    "Bahir Dar",  "02", 11.5742,37.3614, "private",    "+251911234522", False),
    (23, "Mekelle Tigray Pharmacy",    "መቀለ ትግራይ ፋርማሲ",    "Mekelle",    "03", 13.4967,39.4769, "government", "+251911234523", False),
    (24, "Adama Nazret Pharmacy",      "አዳማ ናዝሬት ፋርማሲ",    "Adama",      "01", 8.5400, 39.2700, "private",    "+251911234524", False),
    (25, "Dire Dawa Ras Pharmacy",     "ድሬ ዳዋ ራስ ፋርማሲ",    "Dire Dawa",  "02", 9.5931, 41.8571, "private",    "+251911234525", False),
]

# ─────────────────────────────────────────────
# 2. MEDICINES  (120 with Amharic names + ATC codes)
# ─────────────────────────────────────────────
MEDICINES = [
    # id, name_en, name_am, generic_name, category, atc_code, strength, form, unit_price_etb, essential
    # --- Analgesics / Antipyretics ---
    (1,  "Paracetamol",        "ፓራሲታሞል",         "Paracetamol",       "Analgesic",        "N02BE01", "500mg",    "Tablet",  3.50,  True),
    (2,  "Paracetamol Syrup",  "ፓራሲታሞል ሲሮፕ",    "Paracetamol",       "Analgesic",        "N02BE01", "125mg/5ml","Syrup",   28.00, True),
    (3,  "Ibuprofen",          "አይቡፕሮፌን",         "Ibuprofen",         "NSAID",            "M01AE01", "400mg",    "Tablet",  5.50,  True),
    (4,  "Diclofenac",         "ዲክሎፌናክ",          "Diclofenac sodium", "NSAID",            "M01AB05", "50mg",     "Tablet",  4.00,  True),
    (5,  "Diclofenac Injection","ዲክሎፌናክ መርፌ",    "Diclofenac sodium", "NSAID",            "M01AB05", "75mg/3ml", "Injection",35.00,True),
    (6,  "Aspirin",            "አስፒሪን",            "Acetylsalicylic acid","Analgesic",      "N02BA01", "75mg",     "Tablet",  2.50,  True),
    (7,  "Tramadol",           "ትራማዶል",           "Tramadol HCl",      "Opioid Analgesic", "N02AX02", "50mg",     "Capsule", 12.00, False),
    (8,  "Morphine",           "ሞርፊን",             "Morphine sulfate",  "Opioid Analgesic", "N02AA01", "10mg/ml",  "Injection",85.00,True),

    # --- Antibiotics ---
    (9,  "Amoxicillin",        "አሞክሲሲሊን",         "Amoxicillin",       "Antibiotic",       "J01CA04", "500mg",    "Capsule", 8.00,  True),
    (10, "Amoxicillin Syrup",  "አሞክሲሲሊን ሲሮፕ",    "Amoxicillin",       "Antibiotic",       "J01CA04", "125mg/5ml","Syrup",   45.00, True),
    (11, "Amoxicillin-Clav",   "አሞክሲ-ክላቭ",       "Amoxicillin+Clavulanate","Antibiotic",  "J01CR02", "625mg",    "Tablet",  35.00, True),
    (12, "Azithromycin",       "አዚትሮማይሲን",        "Azithromycin",      "Antibiotic",       "J01FA10", "500mg",    "Tablet",  42.00, True),
    (13, "Ciprofloxacin",      "ሲፕሮፍሎክሳሲን",      "Ciprofloxacin HCl", "Antibiotic",       "J01MA02", "500mg",    "Tablet",  18.00, True),
    (14, "Metronidazole",      "ሜትሮኒዳዞል",         "Metronidazole",     "Antibiotic",       "J01XD01", "400mg",    "Tablet",  4.50,  True),
    (15, "Metronidazole IV",   "ሜትሮኒዳዞል አይቪ",    "Metronidazole",     "Antibiotic",       "J01XD01", "500mg/100ml","IV Bag",120.00,True),
    (16, "Doxycycline",        "ዶክሲሳይክሊን",        "Doxycycline HCl",   "Antibiotic",       "J01AA02", "100mg",    "Capsule", 7.50,  True),
    (17, "Erythromycin",       "ኤሪትሮማይሲን",        "Erythromycin",      "Antibiotic",       "J01FA01", "500mg",    "Tablet",  9.00,  True),
    (18, "Cotrimoxazole",      "ኮትሪሞክሳዞል",        "Sulfamethoxazole+Trimethoprim","Antibiotic","J01EE01","480mg","Tablet",3.00, True),
    (19, "Gentamicin",         "ጀንታሚሲን",          "Gentamicin sulfate","Antibiotic",       "J01GB03", "80mg/2ml", "Injection",25.00,True),
    (20, "Ceftriaxone",        "ሴፍትሪያክሶን",        "Ceftriaxone sodium","Antibiotic",       "J01DD04", "1g",       "Injection",95.00,True),
    (21, "Clindamycin",        "ክሊንዳሚሲን",         "Clindamycin HCl",   "Antibiotic",       "J01FF01", "300mg",    "Capsule", 22.00, True),
    (22, "Tetracycline",       "ቴትራሳይክሊን",        "Tetracycline HCl",  "Antibiotic",       "J01AA07", "250mg",    "Capsule", 4.00,  True),

    # --- Antimalarials ---
    (23, "Artemether-Lume",    "አርቴሜተር-ሉሜ",      "Artemether+Lumefantrine","Antimalarial","P01BF01","20/120mg","Tablet",75.00, True),
    (24, "Chloroquine",        "ክሎሮኩዊን",          "Chloroquine phosphate","Antimalarial",  "P01BA01", "250mg",    "Tablet",  5.00,  True),
    (25, "Quinine",            "ኩዊኒን",             "Quinine sulfate",   "Antimalarial",    "P01BC01", "300mg",    "Tablet",  6.50,  True),

    # --- Antituberculosis ---
    (26, "Rifampicin",         "ሪፋምፒሲን",          "Rifampicin",        "Anti-TB",          "J04AB02", "600mg",    "Capsule", 45.00, True),
    (27, "Isoniazid",          "አይሶኒያዚድ",         "Isoniazid",         "Anti-TB",          "J04AC01", "300mg",    "Tablet",  8.00,  True),
    (28, "Ethambutol",         "ኤታምቡቶል",          "Ethambutol HCl",    "Anti-TB",          "J04AK02", "400mg",    "Tablet",  12.00, True),
    (29, "Pyrazinamide",       "ፒራዚናሚድ",          "Pyrazinamide",      "Anti-TB",          "J04AK01", "500mg",    "Tablet",  10.00, True),

    # --- Antiretrovirals ---
    (30, "Tenofovir-Lamivu",   "ቴኖፎቪር-ላሚቩ",     "TDF+3TC",           "ARV",              "J05AR08", "300/300mg","Tablet",  120.00,True),
    (31, "Efavirenz",          "ኤፋቪሬንዝ",          "Efavirenz",         "ARV",              "J05AG03", "600mg",    "Tablet",  95.00, True),
    (32, "Lopinavir-Ritonavir","ሎፒናቪር-ሪቶናቪር",  "LPV/r",             "ARV",              "J05AR10", "200/50mg", "Tablet",  145.00,True),

    # --- Antifungals ---
    (33, "Fluconazole",        "ፍሉኮናዞል",          "Fluconazole",       "Antifungal",       "J02AC01", "150mg",    "Capsule", 28.00, True),
    (34, "Griseofulvin",       "ግሪሴኦፉልቪን",       "Griseofulvin",      "Antifungal",       "D01AA08", "500mg",    "Tablet",  18.00, False),
    (35, "Ketoconazole",       "ኬቶኮናዞል",          "Ketoconazole",      "Antifungal",       "J02AB02", "200mg",    "Tablet",  22.00, False),

    # --- Antidiabetics ---
    (36, "Metformin",          "ሜትፎርሚን",          "Metformin HCl",     "Antidiabetic",     "A10BA02", "500mg",    "Tablet",  6.00,  True),
    (37, "Glibenclamide",      "ግሊቤንክላሚድ",       "Glibenclamide",     "Antidiabetic",     "A10BB01", "5mg",      "Tablet",  4.50,  True),
    (38, "Insulin Regular",    "ኢንሱሊን ሬጉላር",     "Insulin human",     "Antidiabetic",     "A10AB01", "100IU/ml", "Vial",    185.00,True),
    (39, "Insulin NPH",        "ኢንሱሊን ኤንፒኤች",    "Insulin isophane",  "Antidiabetic",     "A10AC01", "100IU/ml", "Vial",    185.00,True),

    # --- Antihypertensives / Cardiac ---
    (40, "Amlodipine",         "አምሎዲፒን",          "Amlodipine besylate","Antihypertensive","C08CA01","5mg",      "Tablet",  8.50,  True),
    (41, "Enalapril",          "ኢናላፕሪል",          "Enalapril maleate", "Antihypertensive", "C09AA02", "5mg",      "Tablet",  7.00,  True),
    (42, "Hydrochlorothiazide","ሃይድሮክሎሮቲያዚድ",   "Hydrochlorothiazide","Diuretic",        "C03AA03", "25mg",     "Tablet",  3.50,  True),
    (43, "Atenolol",           "አቴኖሎል",            "Atenolol",          "Beta-blocker",     "C07AB03", "50mg",     "Tablet",  5.00,  True),
    (44, "Nifedipine",         "ኒፌዲፒን",            "Nifedipine",        "Antihypertensive", "C08CA05", "10mg",     "Capsule", 6.00,  True),
    (45, "Furosemide",         "ፉሮሴሚድ",            "Furosemide",        "Diuretic",         "C03CA01", "40mg",     "Tablet",  3.50,  True),
    (46, "Furosemide Inj",     "ፉሮሴሚድ መርፌ",      "Furosemide",        "Diuretic",         "C03CA01", "20mg/2ml", "Injection",18.00,True),
    (47, "Digoxin",            "ዲጎክሲን",            "Digoxin",           "Cardiac glycoside","C01AA05", "0.25mg",   "Tablet",  5.50,  True),
    (48, "Propranolol",        "ፕሮፕራኖሎል",         "Propranolol HCl",   "Beta-blocker",     "C07AA05", "40mg",     "Tablet",  4.50,  True),

    # --- GI / ORS ---
    (49, "ORS",                "ኦአርኤስ",            "Oral Rehydration Salts","GI",            "A07CA",   "20.5g",    "Sachet",  5.00,  True),
    (50, "Zinc Sulfate",       "ዚንክ ሰልፌት",        "Zinc sulfate",      "GI / Supplement",  "A12CB01", "20mg",     "Tablet",  4.00,  True),
    (51, "Omeprazole",         "ኦሜፕራዞል",          "Omeprazole",        "PPI",              "A02BC01", "20mg",     "Capsule", 12.00, True),
    (52, "Ranitidine",         "ራኒቲዲን",            "Ranitidine HCl",    "H2 blocker",       "A02BA02", "150mg",    "Tablet",  6.00,  True),
    (53, "Metoclopramide",     "ሜቶክሎፕራሚድ",       "Metoclopramide HCl","Antiemetic",       "A03FA01", "10mg",     "Tablet",  4.50,  True),
    (54, "Loperamide",         "ሎፔራሚድ",           "Loperamide HCl",    "Antidiarrhoeal",   "A07DA03", "2mg",      "Capsule", 5.00,  True),
    (55, "Antacid",            "አንታሲድ",            "Aluminium hydroxide+Mg","Antacid",      "A02AA04", "200/200mg","Tablet",  3.00,  False),
    (56, "Bisacodyl",          "ቢሳኮዲል",            "Bisacodyl",         "Laxative",         "A06AB02", "5mg",      "Tablet",  4.00,  False),

    # --- Respiratory ---
    (57, "Salbutamol Inhaler", "ሳልቡታሞል ኢንሃለር",  "Salbutamol",        "Bronchodilator",   "R03AC02", "100mcg",   "Inhaler", 95.00, True),
    (58, "Salbutamol Syrup",   "ሳልቡታሞል ሲሮፕ",    "Salbutamol",        "Bronchodilator",   "R03AC02", "2mg/5ml",  "Syrup",   45.00, True),
    (59, "Beclomethasone Inh", "ቤክሎሜታዞን ኢንሃለር", "Beclomethasone",    "Corticosteroid",   "R03BA01", "250mcg",   "Inhaler", 185.00,True),
    (60, "Theophylline",       "ቴዎፊሊን",           "Theophylline",      "Bronchodilator",   "R03DA04", "200mg",    "Tablet",  8.00,  True),
    (61, "Prednisolone",       "ፕሬድኒሶሎን",         "Prednisolone",      "Corticosteroid",   "H02AB06", "5mg",      "Tablet",  5.00,  True),
    (62, "Dexamethasone",      "ዴክሳሜታዞን",         "Dexamethasone",     "Corticosteroid",   "H02AB02", "4mg",      "Tablet",  4.50,  True),
    (63, "Dexamethasone Inj",  "ዴክሳሜታዞን መርፌ",   "Dexamethasone",     "Corticosteroid",   "H02AB02", "8mg/2ml",  "Injection",28.00,True),

    # --- Vitamins / Supplements ---
    (64, "Vitamin A",          "ቪታሚን ኤ",          "Retinol",           "Vitamin",          "A11CA01", "200,000IU","Capsule", 5.00,  True),
    (65, "Folic Acid",         "ፎሊክ አሲድ",         "Folic acid",        "Vitamin",          "B03BB01", "5mg",      "Tablet",  2.50,  True),
    (66, "Vitamin B Complex",  "ቪታሚን ቢ ኮምፕሌክስ","B-complex vitamins","Vitamin",           "A11BA",   "standard", "Tablet",  3.50,  False),
    (67, "Ferrous Sulfate",    "ፌሮስ ሰልፌት",        "Ferrous sulfate",   "Iron supplement",  "B03AA07", "200mg",    "Tablet",  3.00,  True),
    (68, "Calcium Carbonate",  "ካልሲየም ካርቦኔት",   "Calcium carbonate", "Mineral",           "A12AA04", "500mg",    "Tablet",  5.00,  False),

    # --- Antiparasitics ---
    (69, "Albendazole",        "አልቤንዳዞል",         "Albendazole",       "Anthelmintic",     "P02CA03", "400mg",    "Tablet",  8.00,  True),
    (70, "Mebendazole",        "ሜቤንዳዞል",          "Mebendazole",       "Anthelmintic",     "P02CA01", "500mg",    "Tablet",  6.00,  True),
    (71, "Praziquantel",       "ፕራዚኩዋንቴል",        "Praziquantel",      "Anthelmintic",     "P02BA01", "600mg",    "Tablet",  22.00, True),
    (72, "Permethrin Cream",   "ፐርሜትሪን ክሬም",     "Permethrin",        "Antiparasitic",    "P03AC04", "5%",       "Cream",   65.00, False),

    # --- Neurological / Psychiatric ---
    (73, "Phenobarbital",      "ፌኖባርቢታል",         "Phenobarbital",     "Antiepileptic",    "N03AA02", "100mg",    "Tablet",  5.50,  True),
    (74, "Carbamazepine",      "ካርባማዜፒን",         "Carbamazepine",     "Antiepileptic",    "N03AF01", "200mg",    "Tablet",  8.00,  True),
    (75, "Valproic Acid",      "ቫልፕሮኢክ አሲድ",     "Valproate sodium",  "Antiepileptic",    "N03AG01", "500mg",    "Tablet",  18.00, True),
    (76, "Diazepam",           "ዲያዜፓም",            "Diazepam",          "Anxiolytic",       "N05BA01", "5mg",      "Tablet",  4.00,  True),
    (77, "Diazepam Inj",       "ዲያዜፓም መርፌ",      "Diazepam",          "Anxiolytic",       "N05BA01", "10mg/2ml", "Injection",22.00,True),
    (78, "Haloperidol",        "ሃሎፔሪዶል",           "Haloperidol",       "Antipsychotic",    "N05AD01", "5mg",      "Tablet",  7.00,  True),
    (79, "Chlorpromazine",     "ክሎርፕሮማዚን",       "Chlorpromazine HCl","Antipsychotic",    "N05AA01", "100mg",    "Tablet",  6.50,  True),
    (80, "Amitriptyline",      "አሚትሪፕቲሊን",        "Amitriptyline HCl", "Antidepressant",   "N06AA09", "25mg",     "Tablet",  5.00,  True),

    # --- Ophthalmological ---
    (81, "Tetracycline Eye",   "ቴትራሳይክሊን ዓይን",  "Tetracycline",      "Ophthalmic",       "S01AA09", "1%",       "Eye Oint",28.00, True),
    (82, "Chloramphenicol Eye","ክሎራምፌኒኮል ዓይን", "Chloramphenicol",   "Ophthalmic",       "S01AA01", "0.5%",     "Eye Drop", 25.00, True),
    (83, "Tropicamide",        "ትሮፒካሚድ",          "Tropicamide",       "Ophthalmic",       "S01FA06", "1%",       "Eye Drop", 45.00, False),

    # --- Dermatological ---
    (84, "Hydrocortisone Cream","ሃይድሮኮርቲዞን ክሬም","Hydrocortisone",    "Dermatological",   "D07AA02", "1%",       "Cream",   35.00, True),
    (85, "Gentian Violet",     "ጀንሺያን ቫዮሌት",     "Crystal violet",    "Antiseptic",       "D08AJ01", "0.5%",     "Solution",18.00, True),
    (86, "Povidone Iodine",    "ፖቪዶን አዮዲን",       "Povidone-iodine",   "Antiseptic",       "D08AG02", "10%",      "Solution",32.00, True),
    (87, "Calamine Lotion",    "ካላሚን ሎሽን",        "Calamine",          "Dermatological",   "D04",     "15%",      "Lotion",  28.00, False),

    # --- Reproductive / Maternal ---
    (88, "Oxytocin",           "ኦክሲቶሲን",          "Oxytocin",          "Uterotonic",       "H01BB02", "10IU/ml",  "Injection",35.00,True),
    (89, "Magnesium Sulfate",  "ማግኒዚየም ሰልፌት",   "Magnesium sulfate", "Eclampsia Rx",     "A12CC02", "50%",      "Injection",55.00,True),
    (90, "Combined OCP",       "ተቀናጅቶ የወሊድ ቁጥጥር","Ethinyl Estradiol+Levonorgestrel","Contraceptive","G03AA07","30/150mcg","Tablet",8.00,True),
    (91, "Medroxyprogesterone","ሜድሮክሲ ፕሮጅስቴሮን","Medroxyprogesterone","Injectable Contraceptive","G03AC06","150mg/ml","Injection",45.00,True),

    # --- Vaccines / Biologicals ---
    (92, "Oral Rehydration Salts Low-Os","ኦአርኤስ ሎ-ኦስ","ORS low osmolarity","GI",     "A07CA",   "20g",      "Sachet",  6.00,  True),

    # --- IV Fluids ---
    (93, "Normal Saline 0.9%", "ኖርማል ሴላይን",      "Sodium Chloride 0.9%","IV Fluid",     "B05CB01", "500ml",    "IV Bag",  65.00, True),
    (94, "Ringer's Lactate",   "ሪንገርስ ላክቴት",     "Lactated Ringer's", "IV Fluid",         "B05BB01", "500ml",    "IV Bag",  70.00, True),
    (95, "Dextrose 5%",        "ዴክስትሮዝ 5%",       "Glucose 5%",        "IV Fluid",         "B05BA03", "500ml",    "IV Bag",  65.00, True),
    (96, "Dextrose 50%",       "ዴክስትሮዝ 50%",      "Glucose 50%",       "IV Fluid",         "B05BA03", "50ml",     "IV Bag",  45.00, True),

    # --- Surgical / Emergency ---
    (97, "Ketamine",           "ኬታሚን",             "Ketamine HCl",      "Anaesthetic",      "N01AX03", "500mg/10ml","Injection",185.00,True),
    (98, "Lidocaine",          "ሊዶካይን",            "Lidocaine HCl",     "Local Anaesthetic","N01BB02","2%",        "Injection",35.00,True),
    (99, "Adrenaline",         "አድሬናሊን",           "Epinephrine",       "Emergency",        "C01CA24", "1mg/ml",   "Injection",28.00,True),
    (100,"Atropine",           "አትሮፒን",             "Atropine sulfate",  "Anticholinergic",  "A03BA01", "0.5mg/ml", "Injection",22.00,True),

    # --- Additional common ---
    (101,"Chlorphenamine",     "ክሎርፌናሚን",         "Chlorphenamine maleate","Antihistamine","R06AB02","4mg",      "Tablet",  3.50,  True),
    (102,"Cetirizine",         "ሴቲሪዚን",            "Cetirizine HCl",    "Antihistamine",    "R06AE07", "10mg",     "Tablet",  8.00,  False),
    (103,"Multivitamin",       "ሙልቲቪታሚን",         "Multivitamin",      "Supplement",       "A11AA03", "standard", "Tablet",  4.50,  False),
    (104,"Vitamin C",          "ቪታሚን ሲ",           "Ascorbic acid",     "Vitamin",          "A11GA01", "500mg",    "Tablet",  4.00,  False),
    (105,"Heparin",            "ሄፓሪን",              "Heparin sodium",    "Anticoagulant",    "B01AB01", "5000IU/ml","Injection",95.00,True),
    (106,"Warfarin",           "ዋርፋሪን",             "Warfarin sodium",   "Anticoagulant",    "B01AA03", "5mg",      "Tablet",  12.00, True),
    (107,"Atorvastatin",       "አቶርቫስታቲን",        "Atorvastatin calcium","Statin",         "C10AA05", "20mg",     "Tablet",  22.00, True),
    (108,"Simvastatin",        "ሲምቫስታቲን",         "Simvastatin",       "Statin",           "C10AA01", "20mg",     "Tablet",  18.00, True),
    (109,"Loratadine",         "ሎራታዲን",            "Loratadine",        "Antihistamine",    "R06AX13", "10mg",     "Tablet",  9.00,  False),
    (110,"Nystatin",           "ናይስታቲን",           "Nystatin",          "Antifungal",       "A07AA02", "500,000IU","Tablet",  8.00,  True),
    (111,"Acyclovir",          "አሲክሎቪር",           "Acyclovir",         "Antiviral",        "J05AB01", "200mg",    "Tablet",  15.00, True),
    (112,"Methotrexate",       "ሜቶትሬክሳት",         "Methotrexate",      "Antineoplastic",   "L01BA01", "2.5mg",    "Tablet",  35.00, False),
    (113,"Allopurinol",        "አሎፑሪኖል",           "Allopurinol",       "Gout",             "M04AA01", "300mg",    "Tablet",  8.00,  False),
    (114,"Levothyroxine",      "ሌቮቲሮክሲን",         "Levothyroxine sodium","Thyroid",        "H03AA01", "100mcg",   "Tablet",  12.00, True),
    (115,"Glipizide",          "ግሊፒዚድ",            "Glipizide",         "Antidiabetic",     "A10BB07", "5mg",      "Tablet",  9.00,  False),
    (116,"Spironolactone",     "ስፒሮኖላክቶን",        "Spironolactone",    "Diuretic",         "C03DA01", "25mg",     "Tablet",  10.00, False),
    (117,"Pyridoxine",         "ፒሪዶክሲን",           "Pyridoxine HCl",    "Vitamin",          "A11HA02", "25mg",     "Tablet",  3.50,  True),
    (118,"Clotrimazole",       "ክሎትሪማዞል",         "Clotrimazole",      "Antifungal",       "D01AC01", "1%",       "Cream",   35.00, False),
    (119,"Betamethasone Cream","ቤታሜታዞን ክሬም",     "Betamethasone",     "Dermatological",   "D07AC01", "0.1%",     "Cream",   48.00, False),
    (120,"Sodium Bicarbonate", "ሶዲየም ባይካርቦኔት",  "Sodium bicarbonate","Antacid / IV",     "B05XA02", "8.4%",     "Injection",38.00,True),
]

# ─────────────────────────────────────────────
# 3. SEASONAL & DISEASE PATTERNS (for realistic demand)
# ─────────────────────────────────────────────
# Months 1-12; rainy season Jun-Sep, malaria Oct-Nov, cold/flu Dec-Feb
SEASONAL_MULTIPLIERS = {
    # medicine_id : {month: multiplier}
    # Malaria meds spike Oct-Nov
    23: {10: 3.2, 11: 2.8, 9: 1.8, 12: 1.2},
    24: {10: 2.9, 11: 2.6, 9: 1.7},
    25: {10: 2.5, 11: 2.2},
    # ORS spikes rainy season (diarrhea)
    49: {6: 2.5, 7: 3.0, 8: 2.8, 9: 2.2, 10: 1.8},
    92: {6: 2.3, 7: 2.8, 8: 2.6, 9: 2.0},
    # Respiratory meds spike cold months
    57: {12: 1.9, 1: 2.1, 2: 1.8, 11: 1.4},
    58: {12: 1.8, 1: 2.0, 2: 1.7},
    60: {12: 1.7, 1: 1.9, 2: 1.6},
    # Antibiotics: always moderate seasonal
    9:  {6: 1.4, 7: 1.5, 8: 1.4},
    12: {6: 1.3, 7: 1.4, 8: 1.3},
}

# Base daily demand per pharmacy (units/day)
BASE_DEMAND = {
    1: 45, 2: 38, 3: 42, 4: 12, 5: 28, 6: 18, 7: 8,
    8: 55, 9: 14, 10: 22, 11: 6,  12: 4,  13: 5,  14: 9,
    15: 35,16: 20, 17: 8,  18: 4,  19: 3,  20: 10,
    21: 18, 22: 12,23: 14, 24: 9,  25: 7,
}

# Most-dispensed medicine categories per pharmacy (weighted)
PHARMACY_FOCUS = {
    # pharma_id: [(medicine_id, relative_weight), ...]  — top medicines
    1:  [(1,10),(9,8),(36,7),(40,6),(51,5),(13,5),(57,4),(49,4)],
    2:  [(1,10),(9,9),(14,8),(49,8),(23,6),(18,6),(50,5)],
    3:  [(1,10),(9,8),(36,7),(40,7),(43,6),(67,5),(57,5)],
    8:  [(1,12),(9,10),(36,8),(40,8),(51,6),(12,6),(57,6),(49,5)],
    15: [(1,10),(9,9),(23,8),(49,9),(18,7),(50,6),(88,5),(89,5)],   # govt
}

def get_demand(pharm_id, med_id, month):
    base = BASE_DEMAND.get(pharm_id, 5)
    # seasonal multiplier
    s = SEASONAL_MULTIPLIERS.get(med_id, {}).get(month, 1.0)
    # medicine popularity weight
    focus = PHARMACY_FOCUS.get(pharm_id, [])
    weight = next((w for mid, w in focus if mid == med_id), 1)
    raw = base * s * weight * random.uniform(0.7, 1.3)
    return max(0, int(raw))

# ─────────────────────────────────────────────
# 4. WRITE CSVs
# ─────────────────────────────────────────────

def write_pharmacies():
    rows = []
    for p in PHARMACIES:
        pid, name, name_am, sub_city, woreda, lat, lon, ptype, phone, open24 = p
        rows.append({
            "id": pid, "name": name, "name_amharic": name_am,
            "sub_city": sub_city, "woreda": woreda,
            "latitude": lat, "longitude": lon,
            "type": ptype, "phone": phone, "open_24h": open24,
            "license_number": f"ETH-PHARM-{pid:04d}",
            "region": "Addis Ababa" if pid <= 20 else ["SNNPR","Amhara","Tigray","Oromia","Dire Dawa"][pid-21]
        })
    write_csv("pharmacies.csv", rows)
    print(f"  ✓ pharmacies.csv — {len(rows)} rows")

def write_medicines():
    rows = []
    for m in MEDICINES:
        mid, name_en, name_am, generic, cat, atc, strength, form, price, essential = m
        rows.append({
            "id": mid, "name_english": name_en, "name_amharic": name_am,
            "generic_name": generic, "category": cat, "atc_code": atc,
            "strength": strength, "dosage_form": form,
            "unit_price_etb": price, "is_essential": essential,
            "requires_prescription": form in ["Injection","IV Bag"] or cat in ["ARV","Anti-TB","Opioid Analgesic","Antiepileptic","Antipsychotic","Antidepressant"],
            "storage_condition": "Refrigerate" if form in ["Vial","IV Bag"] or mid in [38,39] else "Room temperature",
            "shelf_life_months": 24 if form == "Tablet" else (18 if form in ["Capsule","Syrup"] else 12)
        })
    write_csv("medicines.csv", rows)
    print(f"  ✓ medicines.csv — {len(rows)} rows")

def write_inventory():
    rows = []
    iid = 1
    for pid, *_ in PHARMACIES:
        # Each pharmacy stocks 60-80 medicines
        n_medicines = random.randint(60, 80)
        med_ids = random.sample([m[0] for m in MEDICINES], n_medicines)
        for mid in med_ids:
            med = next(m for m in MEDICINES if m[0] == mid)
            price = med[9]
            # Stock level varies — some at risk
            stock_level = random.choices(
                ["out", "critical", "low", "adequate", "overstock"],
                weights=[0.04, 0.08, 0.18, 0.60, 0.10]
            )[0]
            qty_map = {"out": 0, "critical": random.randint(1,10),
                       "low": random.randint(11,30), "adequate": random.randint(31,200),
                       "overstock": random.randint(201,500)}
            qty = qty_map[stock_level]
            reorder_point = random.randint(15, 40)
            rows.append({
                "id": iid, "pharmacy_id": pid, "medicine_id": mid,
                "quantity": qty, "stock_status": stock_level,
                "reorder_point": reorder_point,
                "last_reorder_date": (datetime.now() - timedelta(days=random.randint(1, 45))).strftime("%Y-%m-%d"),
                "expiry_date": (datetime.now() + timedelta(days=random.randint(90, 730))).strftime("%Y-%m-%d"),
                "batch_number": f"BATCH-{pid:02d}-{mid:03d}-{random.randint(1000,9999)}",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            iid += 1
    write_csv("inventory.csv", rows)
    print(f"  ✓ inventory.csv — {len(rows)} rows")
    return rows

def write_transactions(inventory_rows):
    rows = []
    tid = 1
    start_date = datetime.now() - timedelta(days=548)  # ~18 months
    end_date = datetime.now()

    for pid, *_ in PHARMACIES:
        pharm_inv = [r for r in inventory_rows if r["pharmacy_id"] == pid]
        med_ids_in_stock = [r["medicine_id"] for r in pharm_inv]

        current = start_date
        while current <= end_date:
            month = current.month
            # Daily transactions: 10-80 depending on pharmacy size
            n_txns = random.randint(
                max(3, BASE_DEMAND.get(pid, 5) // 4),
                max(8, BASE_DEMAND.get(pid, 5))
            )
            for _ in range(n_txns):
                mid = random.choice(med_ids_in_stock)
                med = next(m for m in MEDICINES if m[0] == mid)
                demand = get_demand(pid, mid, month)
                qty = max(1, demand + random.randint(-2, 2))
                rows.append({
                    "id": tid,
                    "pharmacy_id": pid,
                    "medicine_id": mid,
                    "quantity_dispensed": qty,
                    "unit_price_etb": med[9],
                    "total_price_etb": round(qty * med[9], 2),
                    "transaction_date": current.strftime("%Y-%m-%d"),
                    "month": month,
                    "day_of_week": current.weekday(),
                    "is_weekend": current.weekday() >= 5,
                    "prescription_required": med[9] > 50,
                })
                tid += 1
            current += timedelta(days=1)

    write_csv("transactions.csv", rows)
    print(f"  ✓ transactions.csv — {len(rows)} rows (18 months)")
    return rows

def write_shortage_labels(transaction_rows):
    """Compute weekly demand and label shortage risk — used as ML training target."""
    from collections import defaultdict
    weekly = defaultdict(list)
    for r in transaction_rows:
        d = datetime.strptime(r["transaction_date"], "%Y-%m-%d")
        week_key = (r["pharmacy_id"], r["medicine_id"], d.isocalendar()[0], d.isocalendar()[1])
        weekly[week_key].append(r["quantity_dispensed"])

    rows = []
    sid = 1
    for (pid, mid, year, week), qtys in weekly.items():
        total = sum(qtys)
        avg = total / len(qtys)
        # label: shortage risk if weekly demand > 80th pct of its own history
        # simplified: use absolute thresholds
        risk = "high" if total > 200 else ("medium" if total > 80 else "low")
        rows.append({
            "id": sid, "pharmacy_id": pid, "medicine_id": mid,
            "year": year, "week": week,
            "total_dispensed": total, "avg_daily": round(avg, 2),
            "days_recorded": len(qtys), "shortage_risk": risk
        })
        sid += 1

    write_csv("weekly_demand.csv", rows)
    print(f"  ✓ weekly_demand.csv — {len(rows)} rows (ML training labels)")

def write_outbreak_signals():
    """Inject 3 synthetic outbreak events for anomaly detection training."""
    rows = []
    oid = 1
    # Event 1: ORS spike — diarrhea outbreak, Bole sub-city, July 2024
    for pid in [1, 8, 19, 20]:
        for day_offset in range(14):
            d = datetime(2024, 7, 1) + timedelta(days=day_offset)
            rows.append({
                "id": oid, "pharmacy_id": pid, "medicine_id": 49,
                "quantity_dispensed": random.randint(80, 180),
                "transaction_date": d.strftime("%Y-%m-%d"),
                "is_outbreak_signal": True, "event_name": "Diarrhea_Bole_Jul2024"
            })
            oid += 1
    # Event 2: Salbutamol spike — respiratory infection, citywide, Jan 2025
    for pid in [1, 2, 3, 8, 15]:
        for day_offset in range(10):
            d = datetime(2025, 1, 10) + timedelta(days=day_offset)
            rows.append({
                "id": oid, "pharmacy_id": pid, "medicine_id": 57,
                "quantity_dispensed": random.randint(40, 90),
                "transaction_date": d.strftime("%Y-%m-%d"),
                "is_outbreak_signal": True, "event_name": "Respiratory_Citywide_Jan2025"
            })
            oid += 1
    # Event 3: Artemether spike — malaria, Oct 2024
    for pid in [2, 7, 15, 21]:
        for day_offset in range(21):
            d = datetime(2024, 10, 5) + timedelta(days=day_offset)
            rows.append({
                "id": oid, "pharmacy_id": pid, "medicine_id": 23,
                "quantity_dispensed": random.randint(60, 140),
                "transaction_date": d.strftime("%Y-%m-%d"),
                "is_outbreak_signal": True, "event_name": "Malaria_Oct2024"
            })
            oid += 1
    write_csv("outbreak_signals.csv", rows)
    print(f"  ✓ outbreak_signals.csv — {len(rows)} synthetic outbreak events")

def write_patients():
    FIRST_NAMES_AM = ["አበበ","ቅድስት","ሰሎሞን","ሄለን","ዮሐንስ","ሰናይት","ዳዊት","ፍቅርተ","ሙሉወርቅ","ጌታቸው",
                      "ሚካኤል","ሰብለ","ተካልኝ","ሙሉነሽ","ሲሳይ","ፀሐይ","ቶማስ","አስናቀ","ዘሪሁን","ቃልኪዳን"]
    LAST_NAMES_AM  = ["ሀይሌ","ደስታ","ጌዛ","ወልደ","ተስፋዬ","አለሙ","በዛ","ሙሉጌታ","ካሣ","ይልማ",
                      "አብዱ","ሞጋ","ዘርጋው","ፈለቀ","ሲሳይ","አዱኛ","ዘለቀ","ሻምቤል","ሰሜ","ዋቅጅራ"]
    rows = []
    for i in range(1, 1001):
        fn = random.choice(FIRST_NAMES_AM)
        ln = random.choice(LAST_NAMES_AM)
        rows.append({
            "id": i,
            "name_amharic": f"{fn} {ln}",
            "age": random.randint(1, 85),
            "gender": random.choice(["M", "F"]),
            "sub_city": random.choice(["Bole","Kirkos","Yeka","Addis Ketema","Lideta","Arada","Nifas Silk","Gulele","Kolfe","Akaki"]),
            "phone": f"+2519{random.randint(10000000, 99999999)}",
            "has_chronic_condition": random.random() < 0.22,
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 540))).strftime("%Y-%m-%d")
        })
    write_csv("patients.csv", rows)
    print(f"  ✓ patients.csv — {len(rows)} rows")

def write_prescriptions():
    rows = []
    DIAGNOSES = [
        ("Malaria","ወባ",23), ("Upper RTI","የላይኛው የመተንፈሻ ኅዋ ኢንፌክሽን",9),
        ("Gastroenteritis","የሆድ ቁርጠት",14), ("Hypertension","ደም ግፊት",40),
        ("Diabetes","የስኳር በሽታ",36), ("TB","ሳንባ ነቀርሳ",26),
        ("Pneumonia","ሳንባ ምች",20), ("Malnutrition","የምግብ ዕጥረት",64),
        ("Anaemia","ደም ማነስ",67), ("Epilepsy","የሚጥል በሽታ",73),
    ]
    for i in range(1, 5001):
        diag_en, diag_am, primary_med = random.choice(DIAGNOSES)
        extra_meds = random.sample([m[0] for m in MEDICINES if m[0] != primary_med], random.randint(0, 3))
        rows.append({
            "id": i, "patient_id": random.randint(1, 1000),
            "diagnosis_english": diag_en, "diagnosis_amharic": diag_am,
            "primary_medicine_id": primary_med,
            "additional_medicine_ids": json.dumps(extra_meds),
            "prescribing_facility": random.choice(["Black Lion Hospital","Yekatit 12 Hospital","Tikur Anbessa","St. Paul's Hospital","Zewditu Hospital"]),
            "prescribed_date": (datetime.now() - timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d"),
            "filled": random.random() < 0.78,
            "filled_pharmacy_id": random.randint(1, 25) if random.random() < 0.78 else None
        })
    write_csv("prescriptions.csv", rows)
    print(f"  ✓ prescriptions.csv — {len(rows)} rows")

def write_csv(filename, rows):
    if not rows:
        return
    path = OUT / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

# ─────────────────────────────────────────────
# RUN ALL
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🏥 SmartRx AI — Dataset Generator")
    print("=" * 42)
    write_pharmacies()
    write_medicines()
    inv = write_inventory()
    txn = write_transactions(inv)
    write_shortage_labels(txn)
    write_outbreak_signals()
    write_patients()
    write_prescriptions()
    print("=" * 42)
    print("✅ All datasets generated in backend/datasets/")
