// main.js — students will add JavaScript here as features are built

document.addEventListener('DOMContentLoaded', function () {
    var openBtn = document.getElementById('how-it-works-btn');
    var modal = document.getElementById('how-it-works-modal');
    var closeBtn = document.getElementById('how-it-works-close');
    var video = document.getElementById('how-it-works-video');

    if (!openBtn || !modal || !closeBtn || !video) return;

    var videoSrc = modal.dataset.videoSrc;

    function openModal(e) {
        e.preventDefault();
        video.src = videoSrc + '?autoplay=1';
        modal.classList.add('is-open');
    }

    function closeModal() {
        modal.classList.remove('is-open');
        video.src = '';
    }

    openBtn.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);

    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
    });
});
