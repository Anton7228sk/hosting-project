#!/bin/bash
# Тестування мережевої ізоляції контейнерів

echo "🧪 ТЕСТ ІЗОЛЯЦІЇ КОНТЕЙНЕРІВ"
echo "===================================="
echo ""

# 1. Перевіряємо до яких мереж підключений кожен контейнер
echo "📡 1. Мережі контейнерів:"
echo ""
for container in danylo anna vlad; do
    networks=$(docker inspect $container --format='{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}' 2>/dev/null)
    echo "   $container: $networks"
done
echo ""

# 2. Перевіряємо чи Traefik підключений до всіх ізольованих мереж
echo "📡 2. Мережі Traefik:"
traefik_networks=$(docker inspect traefik_proxy --format='{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}')
echo "   $traefik_networks"
echo ""

# 3. Тестуємо доступ через Traefik (має працювати)
echo "✅ 3. Доступ через Traefik (має працювати):"
for site in danylo anna vlad; do
    status=$(curl -s -o /dev/null -w "%{http_code}" http://${site}.localhost --max-time 3)
    if [ "$status" = "200" ]; then
        echo "   ✅ $site.localhost - OK ($status)"
    else
        echo "   ❌ $site.localhost - FAIL ($status)"
    fi
done
echo ""

# 4. Тестуємо прямий зв'язок між контейнерами (має бути заблоковано)
echo "🚫 4. Прямий зв'язок між контейнерами (має бути заблоковано):"
echo ""

# Спочатку встановлюємо ping в контейнерах
echo "   📦 Встановлення ping..."
docker exec -d danylo sh -c "apt-get update -qq && apt-get install -y -qq iputils-ping 2>&1 > /dev/null" 2>/dev/null
docker exec -d anna sh -c "apt-get update -qq && apt-get install -y -qq iputils-ping 2>&1 > /dev/null" 2>/dev/null
sleep 5

# Отримуємо IP адреси
anna_ip=$(docker inspect anna --format='{{range $key, $value := .NetworkSettings.Networks}}{{if eq $key "anna_isolated"}}{{.IPAddress}}{{end}}{{end}}')
danylo_ip=$(docker inspect danylo --format='{{range $key, $value := .NetworkSettings.Networks}}{{if eq $key "danylo_isolated"}}{{.IPAddress}}{{end}}{{end}}')

echo "   anna IP в anna_isolated: $anna_ip"
echo "   danylo IP в danylo_isolated: $danylo_ip"
echo ""

# Тестуємо ping за назвою
echo "   🔍 danylo -> anna (по назві):"
result=$(docker exec danylo ping -c 2 anna 2>&1 | grep "transmitted")
if [ -z "$result" ]; then
    echo "      ✅ ЗАБЛОКОВАНО (anna недосяжна для danylo)"
else
    echo "      ❌ НЕ ЗАБЛОКОВАНО: $result"
fi

echo ""
echo "   🔍 anna -> danylo (по назві):"
result=$(docker exec anna ping -c 2 danylo 2>&1 | grep "transmitted")
if [ -z "$result" ]; then
    echo "      ✅ ЗАБЛОКОВАНО (danylo недосяжний для anna)"
else
    echo "      ❌ НЕ ЗАБЛОКОВАНО: $result"
fi

echo ""
echo "===================================="
echo "📊 ВИСНОВОК:"
echo ""
echo "Якщо сайти доступні через Traefik (✅) але"
echo "контейнери НЕ можуть пінгувати один одного (✅),"
echo "то ізоляція працює ІДЕАЛЬНО! 🎉"
echo ""
