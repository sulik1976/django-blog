document.addEventListener('DOMContentLoaded', () => {
    console.log('Блог на Django + PostgreSQL готов 🚀');

    // Плавный скролл наверх
    const backToTop = document.getElementById('back-to-top');
    if (backToTop) {
        backToTop.addEventListener('click', (e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});
