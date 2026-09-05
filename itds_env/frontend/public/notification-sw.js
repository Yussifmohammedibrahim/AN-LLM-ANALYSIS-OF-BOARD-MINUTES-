self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = {
      title: 'ITDS Notification',
      body: event.data ? event.data.text() : 'You have a new notification.'
    };
  }

  const title = payload.title || 'ITDS Notification';
  const options = {
    body: payload.body || 'You have a new notification.',
    tag: payload.tag || 'itds-general',
    data: {
      url: payload.url || '/'
    }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const destinationUrl = (event.notification && event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(destinationUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(destinationUrl);
      }
      return null;
    })
  );
});
