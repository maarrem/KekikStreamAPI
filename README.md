# KekikStreamAPI

**[KekikStream](https://github.com/keyiflerolsun/KekikStream)** Projesi ile oluşturulmuş API

## Kullanım

> http://127.0.0.1:3310/api/v1

| Endpoint            | Method | Parametreler                                                                                                 | Açıklama                                                                        | Örnek Kullanım                                                                                  |
|---------------------|--------|--------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| `/get_plugin_names` | GET    | -                                                                                                            | Tüm eklenti isimlerini getirir.                                                 | `/get_plugin_names`                                                                             |
| `/get_plugin`       | GET    | `plugin`: Eklenti adı                                                                                        | Eklenti bilgilerini getirir (ana URL, favicon, açıklama, kategoriler).           | `/get_plugin?plugin=Dizilla`                                                                      |
| `/search`           | GET    | `plugin`: Eklenti adı<br>`query`: Arama sorgusu                                                               | Belirtilen eklenti içinde arama yapar ve sonuçları döner.                       | `/search?plugin=Dizilla&query=film`                                                               |
| `/get_main_page`    | GET    | `plugin`: Eklenti adı<br>`page`: Sayfa numarası<br>`encoded_url`: Kategori URL<br>`encoded_category`: Kategori adı | Belirtilen kategori için ana sayfa içerik listesini döner.                      | `/get_main_page?plugin=Dizilla&page=1&encoded_url=<kategori_url>&encoded_category=<kategori_adı>`  |
| `/load_item`        | GET    | `plugin`: Eklenti adı<br>`encoded_url`: İçerik URL'si                                                        | Seçilen içeriğin detay bilgilerini getirir.                                      | `/load_item?plugin=Dizilla&encoded_url=<icerik_url>`                                              |
| `/load_links`       | GET    | `plugin`: Eklenti adı<br>`encoded_url`: İçerik ya da bölüm URL'si                                             | İçeriğe ait yayın/bağlantı listesini döner.                                      | `/load_links?plugin=Dizilla&encoded_url=<icerik_url>`                                             |
| `/extract`          | GET    | `encoded_url`: Bağlantı<br>`encoded_referer`: Referer URL (genellikle eklentinin ana URL'si)                     | Verilen bağlantıdan oynatılabilir linki ekstrakte eder (gerekliyse).             | `/extract?encoded_url=<link>&encoded_referer=<ana_url>`                                           |