# CI/CD и Kubernetes для цитатника

Есть два независимых учебных контура:

1. **GitLab CI → GitLab Container Registry → Ansible → Ubuntu-сервер с Docker Compose.** Это путь развёртывания приложения на сервере.
2. **Minikube → Kubernetes на компьютере.** Это отдельный стенд для изучения Kubernetes, он не участвует в серверном развёртывании и не запускается из GitLab CI.

## GitLab CI и сервер

Файл `.gitlab-ci.yml` запускает Python-тесты и проверку синтаксиса Ansible. В основной ветке pipeline собирает образы app, notification и frontend, помечает их полным SHA коммита и загружает в GitLab Container Registry. После ручного запуска job `deploy-server` Ansible устанавливает Docker и Compose на Ubuntu, скачивает образы этого коммита, запускает сервисы и проверяет API через Nginx. Серверная Compose-схема использует исходные файлы Nginx и фронтенда из того же коммита; frontend-образ предназначен для Kubernetes.

Что нужно подготовить:

1. Загрузить этот репозиторий в GitLab и включить Container Registry. Нужен GitLab Runner с Docker executor, поддержкой privileged Docker-in-Docker и TLS-каталогом `/certs/client`, как в [инструкции GitLab](https://docs.gitlab.com/ci/docker/docker_in_docker/). Образы собираются только в основной ветке; для остальных веток выполняются проверки.
2. Подготовить отдельный учебный Ubuntu 24.04-сервер с SSH, Python 3, доступом в интернет, свободным портом 8088 и пользователем с `sudo` без запроса пароля. Ansible установит пакеты `docker.io` и `docker-compose-v2`. Серверный адрес и SSH-учётная запись здесь не заданы.
3. В GitLab → Settings → CI/CD → Variables создать защищённые переменные. Секреты также отметить как masked, где GitLab позволяет. Защитить основную ветку и окружение production в настройках проекта.

| Имя | Значение |
| --- | --- |
| `DEPLOY_HOST` | Адрес Ubuntu-сервера без имени пользователя |
| `DEPLOY_USER` | SSH-пользователь с беспарольным sudo |
| `SSH_PRIVATE_KEY` | **File**: приватный ключ SSH; публичный ключ заранее добавить серверу |
| `SSH_KNOWN_HOSTS` | **File**: строка known_hosts сервера с заранее проверенным отпечатком |
| `REGISTRY_DEPLOY_USER` | Имя GitLab deploy token с правом `read_registry` |
| `REGISTRY_DEPLOY_PASSWORD` | Пароль этого deploy token |
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `TELEGRAM_BOT_USERNAME` | Имя бота без `@` (можно не задавать для `KikoRiki_quotes_bot`) |
| `SESSION_COOKIE_SECURE` | `true` после настройки HTTPS; для учебного HTTP оставить `false` |

Сервисные переменные `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD` и `CI_COMMIT_SHA` GitLab предоставляет сам. Доступ к Registry во время сборки и постоянный read-only deploy token для сервера — разные учётные данные. Подробности настройки бота — в [корневом README](../README.md). Не помещай секреты в репозиторий.

4. После успешной сборки основной ветки вручную запусти `deploy-server` в pipeline. Проверь `http://АДРЕС_СЕРВЕРА:8088` и логи на сервере:

   ```bash
   cd /opt/smeshariki/berserk-quotes
   sudo docker compose -f compose.yaml -f ../deploy/compose.images.yaml ps -a
   sudo docker compose -f compose.yaml -f ../deploy/compose.images.yaml logs --tail 50 notification
   ```

Автоматического отката в этом учебном pipeline нет: при ошибке проверь логи; для возврата выбери ранее успешно собранный pipeline и запусти его `deploy-server` после проверки. Данные PostgreSQL и брокеров находятся в Docker volumes. Изменение исходных SQL-файлов не обновляет существующие данные. Серверный Compose использует учебный пароль PostgreSQL и открытую HTTP-страницу; для публичной эксплуатации потребуются отдельная настройка секретов, сети, TLS и резервного копирования.

## Minikube на Windows

Нужны Docker Desktop в режиме Linux-контейнеров, `kubectl`, доступ к интернету и достаточно свободной памяти Docker. Скрипт использует 2 CPU и 4 ГБ для Minikube, а внутри запускает три брокера по 512 МБ. Если одновременно работает Compose-версия, может потребоваться больше памяти.

Из корня репозитория в PowerShell:

```powershell
.\deploy\k8s\start.ps1
```

Скрипт скачивает Minikube в игнорируемую Git папку `.local`, создаёт отдельный профиль `smeshariki`, собирает три локальных образа и применяет Kubernetes-манифесты. Его переменные `MINIKUBE_HOME` и `KUBECONFIG` действуют в текущем окне PowerShell; в новом окне задай их снова:

```powershell
$env:MINIKUBE_HOME = (Resolve-Path .local).Path
$env:KUBECONFIG = Join-Path $env:MINIKUBE_HOME 'kubeconfig'
kubectl -n smeshariki get pods
kubectl -n smeshariki get pvc
.\.local\minikube.exe -p smeshariki service frontend -n smeshariki --url
```

На Windows последняя команда может держать терминал открытым для туннеля: открой показанный ею URL в браузере и оставь команду работать. `notification` и `telegram-bot` по умолчанию выключены до настройки Telegram Secret. После заполнения `berserk-quotes/.env` создай Secret из этого файла и включи их:

```powershell
kubectl -n smeshariki create secret generic telegram --from-env-file=berserk-quotes/.env
kubectl -n smeshariki scale deployment/notification --replicas=1
kubectl -n smeshariki scale deployment/telegram-bot --replicas=1
```

Если Secret уже создан, обнови его через `kubectl` с учётом своих настроек, не записывая значения в репозиторий. Повторный запуск `start.ps1` возвращает оба сервиса к нулю реплик; включи их снова командой `scale`. Одновременно запускай только один `telegram-bot` с данным токеном: перед включением в Kubernetes останови его в Compose (`docker compose stop telegram-bot` из `berserk-quotes`). Для проверки приложения:

```powershell
kubectl -n smeshariki rollout status deployment/app --timeout=180s
kubectl -n smeshariki get statefulset kafka
kubectl -n smeshariki logs deployment/notification
```

Постоянные тома Minikube содержат отдельные от Compose данные. Удаление PVC или профиля Minikube уничтожает данные этого учебного кластера. Три pod брокеров на одной машине не защищают от отказа компьютера. Пароль PostgreSQL в манифесте — учебный. Для публичного или промышленного Kubernetes нужны отдельные секреты, безопасность сети, резервные копии и управляемая конфигурация Kafka/PostgreSQL.
