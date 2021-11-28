Домашнее задание выполнено (-на) для курса [Python Developer. Professional](https://otus.ru/lessons/python-professional/?int_source=courses_catalog&int_term=programming)

# HttpServer

Реализован веб-сервер принимающий GET и HEAD запросы.

Сервер имеет асинхронную архитектуру общения с клиентами.

Обработка запросов происходит в параллельно запущенных воркерах.

##Результаты AB
Server Software:        Python
Server Hostname:        localhost
Server Port:            8080

Document Path:          /
Document Length:        0 bytes

Concurrency Level:      100
Time taken for tests:   22.728 seconds
Complete requests:      50000
Failed requests:        0
Non-2xx responses:      50000
Total transferred:      7450000 bytes
HTML transferred:       0 bytes
Requests per second:    2199.98 [#/sec] (mean)
Time per request:       45.455 [ms] (mean)
Time per request:       0.455 [ms] (mean, across all concurrent requests)
Transfer rate:          320.11 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.3      0       9
Processing:     3   45  11.7     45     112
Waiting:        3   45  11.6     45     112
Total:         12   45  11.7     45     112

Percentage of the requests served within a certain time (ms)
  50%     45
  66%     51
  75%     54
  80%     56
  90%     60
  95%     65
  98%     73
  99%     78
 100%    112 (longest request)
