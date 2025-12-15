"""Moduł do zbierania metryk kontenerów przez Docker API."""
import docker
from web_panel import database


def get_container_stats(container_name):
    """Pobiera aktualne metryki kontenera."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        
        stats = container.stats(stream=False)
        
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                   stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                      stats['precpu_stats']['system_cpu_usage']
        cpu_count = stats['cpu_stats']['online_cpus']
        
        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
        
        ram_usage_mb = stats['memory_stats']['usage'] / (1024 * 1024)
        ram_limit_mb = stats['memory_stats']['limit'] / (1024 * 1024)
        ram_percent = (ram_usage_mb / ram_limit_mb) * 100 if ram_limit_mb > 0 else 0
        
        networks = stats.get('networks', {})
        network_rx_mb = 0
        network_tx_mb = 0
        for interface in networks.values():
            network_rx_mb += interface['rx_bytes'] / (1024 * 1024)
            network_tx_mb += interface['tx_bytes'] / (1024 * 1024)
        
        disk_usage_mb = 0
        try:
            inspect = client.api.inspect_container(container_name)
            size_rw = inspect.get('SizeRw', 0)
            disk_usage_mb = size_rw / (1024 * 1024)
        except:
            pass
        
        return {
            'cpu_percent': round(cpu_percent, 2),
            'ram_usage_mb': round(ram_usage_mb, 2),
            'ram_limit_mb': round(ram_limit_mb, 2),
            'ram_percent': round(ram_percent, 2),
            'network_rx_mb': round(network_rx_mb, 2),
            'network_tx_mb': round(network_tx_mb, 2),
            'disk_usage_mb': round(disk_usage_mb, 2),
            'status': container.status
        }
    except Exception as e:
        print(f"Błąd pobierania metryk dla {container_name}: {e}")
        return None


def get_all_sites_metrics():
    """Pobiera metryki dla wszystkich stron z bazy."""
    sites = database.get_all_sites()
    results = []
    
    for site in sites:
        metrics = get_container_stats(site['name'])
        limits = database.get_resource_limits(site['id'])
        
        if metrics:
            cpu_over_limit = metrics['cpu_percent'] > limits['cpu_limit'] if limits else False
            ram_over_limit = metrics['ram_usage_mb'] > limits['ram_limit_mb'] if limits else False
            disk_over_limit = metrics['disk_usage_mb'] > limits['disk_limit_mb'] if limits else False
            
            results.append({
                'site': site,
                'metrics': metrics,
                'limits': limits,
                'alerts': {
                    'cpu': cpu_over_limit,
                    'ram': ram_over_limit,
                    'disk': disk_over_limit
                }
            })
    
    return results
