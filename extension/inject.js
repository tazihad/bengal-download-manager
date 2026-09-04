// Bengal DM - YouTube & HTML5 Media Bridge (Main World)
(function() {
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
    if (info && info.levels && info.levels.length > 0) {
      window.postMessage({
        type: '__BDM_MEDIA_INFO__',
        data: info
      }, '*');
    }
  }

  window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_MEDIA_INFO__') {
      reportMediaInfo();
    }
  });

  // Watch for player events or state changes
  setInterval(reportMediaInfo, 2500);
})();
