// Choose the supplied desktop shell on a wide initial viewport; mobile variants retain their routes.
if (window.location.pathname === '/' && window.matchMedia('(min-width: 1024px)').matches) {
    window.location.replace('/desktop' + window.location.search);
}
