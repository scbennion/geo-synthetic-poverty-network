import os
from pathlib import Path

# Root of all input and output data. Override with the GSPN_DATA_DIR environment
# variable; defaults to <repo>/data, which is where both the old cwd-relative
# 'data/...' paths and the drivers' '../../data/...' paths pointed.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = os.environ.get('GSPN_DATA_DIR', str(PROJECT_ROOT / 'data'))

RAW_DATA_DIR = os.path.join(DATA_DIR, 'raw-data')

INTERIM_DATA_DIR = os.path.join(DATA_DIR, 'interim-data')

PROCESSED_DATA_DIR = os.path.join(DATA_DIR, 'processed-data')

RESULTS_DIR = os.path.join(DATA_DIR, 'results-data')

state_codes = ['01', '02' , '04', '05', '06', '08', '09', '10', '11', '12', '13', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '44', '45', '46', '47', '48', '49', '50', '51', '53', '54', '55', '56']

state_dict = {
        '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO',
        '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI',
        '16': 'ID', '17': 'IL', '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY',
        '22': 'LA', '23': 'ME', '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN',
        '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH',
        '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND', '39': 'OH',
        '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD',
        '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA',
        '54': 'WV', '55': 'WI', '56': 'WY'
    }
