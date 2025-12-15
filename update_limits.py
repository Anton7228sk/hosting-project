#!/usr/bin/env python3
"""Skrypt do aktualizacji limitów CPU w bazie danych na dynamiczne wartości."""

import sys
sys.path.insert(0, '/app')

from web_panel import database

# Pobierz wszystkie strony
sites = database.get_all_sites()
print(f'Znaleziono {len(sites)} stron')

if len(sites) == 0:
    print('Brak stron w bazie')
    sys.exit(0)

# Oblicz optymalny limit CPU
optimal_cpu = max(10, int(100 / len(sites)))
print(f'Optymalny limit CPU: {optimal_cpu}% (100% / {len(sites)} stron)')

# Aktualizuj limity dla każdej strony
for site in sites:
    print(f'Aktualizuję limity dla {site["name"]}...')
    database.set_resource_limits(
        site['id'], 
        cpu_limit=optimal_cpu,
        ram_limit_mb=512,
        disk_limit_mb=1024,
        bandwidth_limit_mb=10240
    )

print(f'\n✅ Limity zaktualizowane!')
print(f'Nowy limit CPU dla wszystkich: {optimal_cpu}%')
