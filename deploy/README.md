# CI/CD и Kubernetes для цитатника

Есть два независимых учебных контура:

1. **GitLab CI → GitLab Container Registry → Ansible → Ubuntu-сервер с Docker Compose.** Это путь развёртывания приложения на сервере.
2. **Minikube → Kubernetes на компьютере.** Это отдельный стенд для изучения Kubernetes, он не участвует в серверном развёртывании и не запускается из GitLab CI.

## GitLab CI и сервер

Файл `.gitlab-ci.yml` запускает Python-тесты и проверку синтаксиса Ansible. В основной ветке pipeline собирает образы app, notification и frontend, помечает их полным SHA коммита и загружает в GitLab Container Registry. После ручного запуска job `deploy-server` Ansible устанавливает Docker и Compose на Ubuntu, скачивает образы этого коммита, запускает сервисы и проверяет API через Nginx. Серверная Compose-схема использует исходные файлы Nginx и фронтенда из того же коммита; frontend-образ предназначен для Kubernetes.

Что нужно подготовить:

1. Загрузить этот репозиторий в GitLab и включить Container Registry. Нужен GitLab Runner с Docker executor, поддержкой privileged Docker-in-Docker и TLS-каталогом `/certs/client`, как в [инструкции GitLab](https://docs.gitlab.com/ci/docker/docker_in_docker/). Образы собираются только в основной ветке; для остальных веток выполняются проверки.
2. Подготовить Ubuntu 24.04-сервер с SSH, Python 3, доступом в интернет и пользователем с `sudo` без запроса пароля. Указать в DNS домен на адрес сервера и открыть входящие TCP-порты 80 и 443: Caddy получит и обновит публичный сертификат. Ansible установит пакеты `docker.io` и `docker-compose-v2`.
3. В GitLab → Settings → CI/CD → Variables создать защищённые переменные. Секреты также отметить как masked, где GitLab позволяет. Защитить основную ветку и окружение production в настройках проекта.

| Имя | Значение |
| --- | --- |
| `DEPLOY_HOST` | Адрес Ubuntu-сервера без имени пользователя |
| `DEPLOY_USER` | SSH-пользователь с беспарольным sudo |
| `SSH_PRIVATE_KEY` | **File**: приватный ключ SSH; публичный ключ заранее добавить серверу |
| `SSH_KNOWN_HOSTS` | **File**: строка known_hosts сервера с заранее проверенным отпечатком |
| `REGISTRY_DEPLOY_USER` | Имя GitLab deploy token с правом `read_registry` |
| `REGISTRY_DEPLOY_PASSWORD` | Пароль этого deploy token |
| `TELEGRAM_BOT_USERNAME` | Имя бота без `@` (можно не задавать для `KikoRiki_quotes_bot`) |
| `SITE_DOMAIN` | Домен без `https://`, указывающий на сервер |
| `POSTGRES_PASSWORD` | Случайный пароль длиной не менее 32 символов из букв, цифр, `_` и `-`; protected и masked |

При создании сервера Timeweb можно вставить содержимое [`cloud-init.yaml`](cloud-init.yaml) в поле Cloud-init. Оно устанавливает Docker, Compose и Python; SSH-ключ выбирается отдельно в разделе «Авторизация». Проверить завершение настройки после подключения: `cloud-init status --wait`, `docker --version`, `docker compose version` и `systemctl is-active docker`.

Сервисные переменные `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD` и `CI_COMMIT_SHA` GitLab предоставляет сам. Доступ к Registry во время сборки и постоянный read-only deploy token для сервера — разные учётные данные. Подробности настройки бота — в [корневом README](../README.md). Не помещай секреты в репозиторий.

4. После успешной сборки основной ветки вручную запусти `deploy-server` в pipeline. Проверь `https://ДОМЕН` и логи на сервере:

   ```bash
   cd /opt/smeshariki/KikoRiki-quotes
   sudo docker compose -f compose.yaml -f ../deploy/compose.images.yaml -f ../deploy/compose.https.yaml ps -a
   sudo docker compose -f compose.yaml -f ../deploy/compose.images.yaml -f ../deploy/compose.https.yaml logs --tail 50 notification
   ```

Пароль из GitLab сохраняется на сервере в `.secrets/postgres_password` с правами `0600`; Compose монтирует его только нужным контейнерам. Caddy направляет HTTPS на Nginx, а локальные порты приложения и Nginx не опубликованы наружу. На сервере запускаются сайт, база и Kafka. Сервисы `notification` и `telegram-bot` запускаются на компьютере и не получают токен через сервер. Для уже существующего volume без файла секрета playbook остановится: сначала нужно согласованно сменить пароль PostgreSQL и создать секрет. Изменение переменной GitLab само по себе пароль существующей базы не меняет, и playbook не выполняет ротацию автоматически. Автоматического отката и резервного копирования пока нет.

## Сайт на сервере, уведомления на компьютере

На сервере нужно применять Compose-файлы `compose.yaml`, `deploy/compose.images.yaml`, `deploy/compose.https.yaml` и `deploy/compose.remote-server.yaml`. Ansible делает это при запуске `deploy-server` после настройки домена. Брокеры и PostgreSQL слушают дополнительные порты только на `127.0.0.1` сервера; наружу их открывать не нужно. Обработчики Telegram на сервере останавливаются.

На компьютере контейнер SSH создаёт четыре туннеля к серверу. Контейнеры `notification` и `telegram-bot` используют его сетевое пространство, поэтому исходящие запросы к Telegram идут с компьютера. Токен бота хранится в локальном `.env`; на сервер его копировать не нужно. Компьютер и Docker Desktop должны оставаться включены для уведомлений и привязки бота. При недоступности компьютера события остаются в Kafka в пределах срока хранения топика (24 часа), после восстановления соединения consumer продолжит чтение. Запись нажатий зависит от доступности Kafka; повторная доставка в Telegram при сбоях возможна.

Перед запуском:

1. Создай отдельный пароль серверной базы: `py -3.12 KikoRiki-quotes/setup_database.py --remote`. Файл `KikoRiki-quotes/.secrets/remote_postgres_password` игнорируется Git. Для новой серверной базы установи в GitLab защищённую masked-переменную `POSTGRES_PASSWORD` с тем же значением. Не отправляй пароль в чат. Если база сервера уже существует, изменение файла или переменной не меняет её пароль; нужна отдельная согласованная ротация.
2. Укажи `SITE_DOMAIN` в GitLab и выполни серверное развёртывание после настройки DNS. Пока домена нет, эту публичную схему HTTPS запустить не получится.
3. Экспортируй ранее сохранённый SSH host key в отдельный игнорируемый файл, затем сверь отпечаток с отпечатком сервера через консоль Timeweb. Команды для PowerShell из корня проекта:

   ```powershell
   $env:SERVER_IP = '179.252.220.154'
   ssh-keygen -F $env:SERVER_IP -f "$env:USERPROFILE\.ssh\known_hosts" | Where-Object { $_ -notmatch '^#' } | Set-Content -Encoding ascii .local/ssh/timeweb_known_hosts
   ssh-keygen -lf .local/ssh/timeweb_known_hosts
   ```

   В консоли сервера сравни его с `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Если отпечатки не совпадают или файл пустой, не запускай туннель до выяснения причины. Текущий приватный ключ `.local/ssh/timeweb_ed25519` не передавай другим людям.
4. Укажи токен бота в локальном `KikoRiki-quotes/.env`. Останови старый локальный `telegram-bot`, если он работает с этим же токеном: `docker compose -f KikoRiki-quotes/compose.yaml stop telegram-bot notification`. Telegram допускает только один активный обработчик `getUpdates` для одного бота.
5. Из корня проекта запусти туннель и уведомления:

   ```powershell
   $env:SERVER_IP = '179.252.220.154'
   docker compose --env-file KikoRiki-quotes/.env -f deploy/compose.notification-local.yaml up -d --build
   docker compose --env-file KikoRiki-quotes/.env -f deploy/compose.notification-local.yaml logs --tail 50
   ```

   Пока домена нет, серверный сайт можно открыть через этот же туннель по адресу http://localhost:18088. Он доступен только на компьютере. SSH-туннель использует приватный ключ, проверяет host key и автоматически перезапускается при обрыве. Пароль базы берётся из `remote_postgres_password`. Для остановки: `docker compose --env-file KikoRiki-quotes/.env -f deploy/compose.notification-local.yaml down`.

## Локальный HTTPS

После запуска с `compose.https.local.yaml` Caddy создаёт локальный сертификат. Чтобы получить его корневой сертификат для ручной проверки, из `KikoRiki-quotes` выполни:

```powershell
New-Item -ItemType Directory -Force ../.local | Out-Null
docker cp berserk-quotes-caddy-1:/data/caddy/pki/authorities/local/root.crt ../.local/caddy-local-root.crt
curl.exe --noproxy '*' --ssl-no-revoke --cacert ../.local/caddy-local-root.crt https://localhost:8443/api/smeshariki-quotes
```

Параметр `--ssl-no-revoke` нужен для локального центра, который не публикует статус отзыва; проверка подписи и имени сертификата при этом остаётся включена. Браузер по умолчанию не доверяет этому локальному центру сертификации. После проверки, что файл получен из своего контейнера, можно вручную добавить его в хранилище текущего пользователя:

```powershell
Import-Certificate -FilePath ../.local/caddy-local-root.crt -CertStoreLocation Cert:\CurrentUser\Root
```

Это доверие распространяется на сертификаты, выпущенные этим локальным центром; автоматически мы его не устанавливаем. Для публичного домена Caddy получает сертификат от общедоступного центра.

## Minikube на Windows

Нужны Docker Desktop в режиме Linux-контейнеров, `kubectl`, доступ к интернету и достаточно свободной памяти Docker. Скрипт использует 2 CPU и 4 ГБ для Minikube, а внутри запускает три брокера по 512 МБ. Если одновременно работает Compose-версия, может потребоваться больше памяти.

Из корня репозитория в PowerShell:

```powershell
.\deploy\k8s\start.ps1
```

Перед первым запуском создай файл секрета командой `py -3.12 KikoRiki-quotes/setup_database.py`. Скрипт скачивает Minikube в игнорируемую Git папку `.local`, создаёт отдельный профиль `smeshariki`, создаёт Kubernetes Secret `postgres-auth` из файла, собирает образы и применяет манифесты. Если уже существует volume PostgreSQL без `postgres-auth`, скрипт остановится, чтобы не потерять доступ к данным.

Для существующей базы Minikube сначала выбери нужный кластер, задав переменные как ниже в разделе проверки. Затем создай Secret `kubectl -n smeshariki create secret generic postgres-auth --from-file=db_password=KikoRiki-quotes/.secrets/postgres_password` и отдельно смени пароль роли `quotes` в работающей базе на значение из этого файла через `kubectl -n smeshariki exec -it deployment/db -- psql -U quotes -d quotes` и команду `\password quotes`. Ввод пароля в psql не отображается. После этого запусти `start.ps1`: он подключит Secret к подам. Сохрани резервную копию и не изменяй Secret независимо от пароля базы.

Переменные `MINIKUBE_HOME` и `KUBECONFIG` действуют в текущем окне PowerShell; в новом окне задай их снова:

```powershell
$env:MINIKUBE_HOME = (Resolve-Path .local).Path
$env:KUBECONFIG = Join-Path $env:MINIKUBE_HOME 'kubeconfig'
kubectl -n smeshariki get pods
kubectl -n smeshariki get pvc
.\.local\minikube.exe -p smeshariki service frontend -n smeshariki --url
```

На Windows последняя команда может держать терминал открытым для туннеля: открой показанный ею URL в браузере и оставь команду работать. `notification` и `telegram-bot` по умолчанию выключены до настройки Telegram Secret. После заполнения `KikoRiki-quotes/.env` создай Secret из этого файла и включи их:

```powershell
kubectl -n smeshariki create secret generic telegram --from-env-file=KikoRiki-quotes/.env
kubectl -n smeshariki scale deployment/notification --replicas=1
kubectl -n smeshariki scale deployment/telegram-bot --replicas=1
```

Если Secret уже создан, обнови его через `kubectl` с учётом своих настроек, не записывая значения в репозиторий. Повторный запуск `start.ps1` возвращает оба сервиса к нулю реплик; включи их снова командой `scale`. Одновременно запускай только один `telegram-bot` с данным токеном: перед включением в Kubernetes останови его в Compose (`docker compose stop telegram-bot` из `KikoRiki-quotes`). Для проверки приложения:

```powershell
kubectl -n smeshariki rollout status deployment/app --timeout=180s
kubectl -n smeshariki get statefulset kafka
kubectl -n smeshariki logs deployment/notification
```

Постоянные тома Minikube содержат отдельные от Compose данные. Удаление PVC или профиля Minikube уничтожает данные этого учебного кластера. Три pod брокеров на одной машине не защищают от отказа компьютера. Kubernetes Secret доступен пользователям с соответствующими правами к API и сам по себе не заменяет настроенное шифрование etcd и RBAC. Публичный HTTPS настроен для серверного Compose; Minikube остаётся локальным HTTP-стендом.
