// Bengal DM - YouTube media info bridge (MAIN world)
// Facebook has its own module under src/sites/facebook.
(function () {
  const host = window.location.hostname.toLowerCase();
  const isYouTube = host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtu.be';
  if (!isYouTube) return;

  function getYouTubeMediaInfo() {
    try {
      const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
      if (!player) return null;

      const levels = (typeof player.getAvailableQualityLevels === 'function')
        ? player.getAvailableQualityLevels()
        : [];

      const videoData = (typeof player.getVideoData === 'function')
        ? player.getVideoData()
        : {};

      const duration = (typeof player.getDuration === 'function')
        ? player.getDuration()
        : 0;

      return {
        levels: Array.isArray(levels) ? levels : [],
        title: videoData.title || document.title,
        author: videoData.author || "",
        videoId: videoData.video_id || "",
        duration: duration || 0
      };
    } catch (e) {
      return null;
    }
  }

  function reportMediaInfo() {
    const info = getYouTubeMediaInfo();
    if (!info) return;
    window.postMessage({
      type: '__BDM_MEDIA_INFO__',
      data: info
    }, '*');
  }

  window.addEventListener('message', function (event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_MEDIA_INFO__') {
      reportMediaInfo();
    }
  });

  setInterval(reportMediaInfo, 2500);
})();
