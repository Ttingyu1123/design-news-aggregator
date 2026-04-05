const CACHE_NAME = 'design-news-cache-v1';
const urlsToCache = [
    './',
    './index.html',
    './style.css',
    'https://cdn.jsdelivr.net/npm/marked/marked.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return cache.addAll(urlsToCache);
            })
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
});

self.addEventListener('fetch', event => {
    // 對於 API 或動態 Markdown 不作快取，確保永遠抓到最新的
    if (event.request.url.includes('.md') || event.request.url.includes('index.json')) {
        return fetch(event.request).catch(() => caches.match(event.request));
    }

    // 其他靜態資源快取優先
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});
