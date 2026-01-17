#!/usr/bin/env python3
"""
Valley-based HRR detection test.

Find valleys (local minima) in HR, look back to find the preceding max.
"""

import numpy as np
from scipy import signal
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path


def test_valley_detection(session_id: int = 51):
    load_dotenv(Path(__file__).parent.parent / '.env')
    
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'arnold_analytics'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '')
    )
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT hr_value 
            FROM hr_samples 
            WHERE session_id = %s 
            ORDER BY sample_time
        """, (session_id,))
        rows = cur.fetchall()
    
    hr_values = np.array([r[0] for r in rows])
    resting_hr = 55
    
    print(f"Session {session_id}: {len(hr_values)} samples ({len(hr_values)/60:.1f} min)")
    print(f"HR range: {hr_values.min()} - {hr_values.max()}")
    
    # Smooth slightly to reduce noise
    kernel = np.ones(5) / 5
    hr_smooth = np.convolve(hr_values, kernel, mode='same')
    
    # Find valleys (invert signal, find peaks)
    valleys, props = signal.find_peaks(-hr_smooth, prominence=10, distance=60)
    
    print(f"\nValleys found: {len(valleys)}")
    print("-" * 60)
    
    for valley_idx in valleys:
        valley_hr = hr_values[valley_idx]
        
        # Look back up to 5 min to find max
        lookback = min(valley_idx, 300)
        search_window = hr_values[valley_idx - lookback:valley_idx]
        
        if len(search_window) == 0:
            continue
            
        local_max_idx = np.argmax(search_window)
        max_idx = valley_idx - lookback + local_max_idx
        max_hr = hr_values[max_idx]
        
        drop = max_hr - valley_hr
        
        # Filter: must be elevated above resting and have real drop
        if max_hr < resting_hr + 25:
            continue
        if drop < 12:
            continue
        
        max_min = max_idx // 60
        max_sec = max_idx % 60
        valley_min = valley_idx // 60
        valley_sec = valley_idx % 60
        
        print(f"  Max {max_min:02d}:{max_sec:02d} (HR {max_hr}) → Valley {valley_min:02d}:{valley_sec:02d} (HR {valley_hr}) | drop {drop}")
    
    conn.close()


if __name__ == '__main__':
    import sys
    session_id = int(sys.argv[1]) if len(sys.argv) > 1 else 51
    test_valley_detection(session_id)
