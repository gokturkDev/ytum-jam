# Konudan session kapsamlı reform üretimi

Server, hazır katalogdan reform seçmenin yanında oyuncunun verdiği konudan oynanmaya hazır
bir reform üretebilir. Aynı `POST /v2/games` endpoint'i ve `GameView` yanıtı kullanılır.

```sh
curl -sS http://127.0.0.1:8000/v2/games \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Köylerde ortak fırın kurulması"}'
```

Başarılı yanıt `201 Created` döner. `scenario` içinde üretilen başlık, kararname, halka açık
bilgiler ve oyun kuralları; `current_objections` içinde ilk turun itirazları bulunur.
`allowed_actions` değeri `["submit_answer"]` olur. Oyuncu hemen normal cevap akışına geçebilir:

```sh
curl -sS http://127.0.0.1:8000/v2/games/GAME_ID/answers \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"aceb710b-f839-4ba1-b149-fb93c52bdad0","expected_version":0,"text":"Fırını sırayla kullanıp masrafları paylaşabiliriz."}'
```

`GAME_ID` yerine oluşturma yanıtındaki `game_id` yazılır. Her yeni cevap için yeni bir UUID
ve son yanıttaki `version` kullanılır. Başarılı cevabı yeniden almak için aynı istek gövdesi
ve UUID tekrar gönderilebilir. Okuma ve sonuç ekranı dahil sonraki bütün işlemler mevcut
[v2 protokolünü](protocol.md) izler.

## İstek ve session ömrü

- `topic`, başındaki ve sonundaki boşluklar temizlendikten sonra 1-500 Unicode karakter
  içeren bir string olmalıdır. Sadece boşluk içeren girdiler reddedilir.
- `scenario_id` ve `topic` alanlarından tam biri null olmayan bir değer taşımalıdır.
  Örneğin `{"scenario_id":"schooling_v1"}` hazır reform başlatmaya devam eder.
- Kurallar, karakterler, puanlar veya itirazlar istemciden alınmaz. Bilinmeyen alanlar ve
  geçersiz istekler provider çağrısı yapılmadan `422 INVALID_INPUT` döner.
- Her oluşturma ayrı `game_id` ve `generated_` önekli ayrı `scenario.id` üretir. Aynı
  konuyu göndermek mevcut oyunu yeniden kullanmaz.
- Üretilen reform yalnızca o oyunun bellekteki durumunda yaşar. `GET /v2/scenarios`
  kataloğuna eklenmez, `reforms.json` değiştirilmez ve bu `scenario.id` ile başka bir oyun
  başlatılamaz. Session'ı tekrar açmak için `GET /v2/games/{game_id}` kullanılır.
- Sunucu yeniden başlatıldığında oyun kaybolur. Mevcut bellek deposu için tek server
  process/worker kullanılmalıdır. `TRANSCRIPT_DIR` açıksa mevcut davranış gereği cevap
  geçmişi diske yazılabilir; bu, reform kataloğu veya yeniden yüklenebilir session kaydı değildir.
- Oluşturma isteğinde replay/idempotency anahtarı yoktur. Yanıt ağda kaybolursa aynı konuyla
  tekrar oluşturma yeni bir oyun ve yeni provider çağrıları başlatabilir.

## Üretilen içerik ve oyun kuralları

İlk model çağrısı Türkçe başlığı, reformun sabit amacını anlatan kararnameyi, Türkçe halka
açık bilgileri ve evaluator için İngilizce kanonik dünya bilgilerini üretir. Bu ortak bağlam
tamamlandıktan sonra server'da yapılandırılmış her karakter için üç farklı, reforma özgü
itiraz üretilir. Karakter profilleri `PERSONAS_FILE` veya mevcut karakter kataloğundan gelir.

İtirazlar mevcut kısa cümle sözleşmesine uyar: her biri tek cümle ve en fazla 180 karakterdir.
İlk turun karakterleri `OBJECTIONS_MIN` / `OBJECTIONS_MAX` ayarlarıyla seçilir; seçilen her
karakterin ilk itirazı doğrudan gösterilir. Sonraki turlarda mevcut evaluator, bu reformun
bilgilerini, karaktere özgü örnekleri ve oyun geçmişini kullanarak yeni itiraz üretir.

Kurallar model tarafından belirlenmez. Üretilen reformlar varsayılan olarak %30 destekle
başlar, %60 hedefle üç tur oynanır. `STARTING_SUPPORT`, `TARGET_SUPPORT` ve `MAX_ROUNDS`
ayarları varsa bunlar uygulanır. Puanlama ve kazanma koşulları mevcut oyunla aynıdır.
Üretilen reformlarda `visual_effect` null ve sonuçtaki `visual_effects` boş listedir;
yeni sprite veya frontend efekt uygulaması üretilmez.

Konu, modele sistem talimatı olarak eklenmez; JSON içindeki güvenilmeyen veri olarak
gönderilir. Üretim promptları, rol/şema değiştirme taleplerini yok sayıp reform konusunu
kullanmalarını ister. Çıktılar Structured Outputs ve server tarafı doğrulamayla denetlenir.

## Concurrency ve gecikme

Üretim akışı iki bağımlılık katmanından oluşur:

1. Bir reform taslağı çağrısı.
2. Karakter başına bir itiraz paketi çağrısı; bu çağrılar `asyncio.TaskGroup` ile paralel yürür.

İkinci katman ilk katmanın kanonik bilgilerini kullanır. Bu sıralama karakterlerin farklı
reform ayrıntıları uydurmasını azaltır. İlk itirazlar zaten ikinci katmanda üretildiğinden,
oyunu başlatmak için ayrıca bir ilk tur çağrısı yapılmaz. N karakter için retriesiz toplam
provider çağrı sayısı `1 + N` olur. Varsayılan üç karakter ve concurrency 3 ile itirazların
üçü aynı anda üretilebilir.

`PROVIDER_CONCURRENCY`, bütün session'ların reform üretimi, cevap değerlendirmesi ve
sonraki tur üretimi için paylaşılan tek semaphore sınırıdır. Her session için ayrı limit
açılmaz; bir provider slotunu tutan üst işlem, çocuk çağrıları beklemez. Concurrency 1
ile de akış tamamlanır. Başka trafik yokken ve limit karakter sayısına yeterliyken yaklaşık
kritik yol, taslak süresi + en yavaş karakter çağrısıdır. Daha düşük limitte karakterler
dalgalar halinde çalışır. Gerçek gecikme modele, provider kapasitesine, retry ve kuyruk
beklemelerine bağlıdır; burada canlı provider gecikmesi için bir SLA verilmez.

| Ayar | Varsayılan | Kapsam |
| --- | --- | --- |
| `PROVIDER_CONCURRENCY` | 3 | Server genelinde eşzamanlı provider çağrısı sınırı |
| `PROVIDER_TIMEOUT_SECONDS` | 30 | Slot alındıktan sonra tek çağrı denemesinin süresi |
| `GENERATION_TIMEOUT_SECONDS` | 75 | Kuyruklar ve retry dahil konudan oyun oluşturmaya toplam süre |
| `TURN_TIMEOUT_SECONDS` | 75 | Hazır reformla başlatma ve normal cevap işlemlerinin toplam süresi |
| `MAX_OUTPUT_TOKENS` | 1200 | Her provider çağrısının çıktı bütçesi |

İstemcinin HTTP timeout'u `GENERATION_TIMEOUT_SECONDS` değerinden büyük olmalıdır.
Ayarlamalar server yeniden başlatıldığında uygulanır. Büyük karakter listelerinde kuyruk
süresi de toplam deadline'a dahildir.

## Hata ve iptal davranışı

Yalnızca bütün içerik ve ilk tur hazır olduğunda oyun depoya eklenir. Başarısız üretim,
kısmi oyun veya katalog girdisi bırakmaz. Bir karakter çağrısı nihai olarak başarısız olursa
TaskGroup kardeş çağrıları iptal eder ve kapanmalarını bekler. Toplam timeout veya coroutine
iptali de aynı temizliği yapar ve semaphore slotlarını serbest bırakır. HTTP bağlantısının
kopması tek başına ASGI handler'ının iptal edileceğini garanti etmez; toplam deadline sınırı
her durumda geçerlidir.

Her provider işlemi geçici hatalarda en fazla bir kez yeniden denenir; başarılı taslak ve
başarılı karakter çağrıları tekrar çalıştırılmaz. SDK retry'ları kapalıdır. Mevcut provider
hata kodları ve `retryable` alanı korunur; şema/cümle doğrulama hataları mevcut
`INVALID_FACEOFF_OUTPUT` kodunu kullanır. Ek kodlar:

| HTTP | Kod | Anlam |
| --- | --- | --- |
| 504 | `GENERATION_TIMEOUT` | Toplam üretim süresi aşıldı; tekrar denenebilir |
| 503 | `GENERATION_UNAVAILABLE` | Enjekte edilen GameService üzerinde reform generator yapılandırılmamış |

Standart `create_app` hem OpenAI hem fake backend için generator'ı bağlar. `fake` modu
API entegrasyonunu anahtarsız denemek içindir; yapay zeka kalitesini veya canlı model hızını
temsil etmez. Model ayarları mevcut `LLM_BACKEND`, `OPENAI_MODEL` ve `OPENAI_API_KEY` üzerinden
kullanılır. Loglar çağrı türünü, deneme sayısını, gecikmeyi ve provider kullanımını içerir.

## Doğrulama

`tests/test_generated_reforms.py`, HTTP üzerinden konudan tamamlanmış oyuna akışı, session
izolasyonunu, katalog değişmezliğini, ayarları, girdi doğrulamasını, session'lar ve mevcut
oyunlarla ortak concurrency sınırını, kısmi retry'ı, hata/timeout/iptal temizliğini sınar.
`tests/test_openai.py`, gerçek SDK'nın yeni şemaları parse etmesini sahte HTTP provider
yanıtlarıyla doğrular. Canlı modelin içerik kalitesi ve gecikmesi bu testlerden çıkarılamaz.
