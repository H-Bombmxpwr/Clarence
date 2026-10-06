# Lavalink server for Clarence. Deploy this folder as its own Railway service with App Sleeping
# (Settings -> Serverless) turned on: the bot only connects while music is playing, so it sleeps otherwise.
FROM ghcr.io/lavalink-devs/lavalink:4.2.2
COPY application.yml /opt/Lavalink/application.yml
# Bake the plugins into the image so a cold start doesn't re-download them every wake-up.
# Keep these versions in sync with lavalink.plugins in application.yml.
ADD --chmod=644 https://maven.lavalink.dev/releases/dev/lavalink/youtube/youtube-plugin/1.18.2/youtube-plugin-1.18.2.jar /opt/Lavalink/plugins/
ADD --chmod=644 https://maven.lavalink.dev/releases/com/github/topi314/lavasrc/lavasrc-plugin/4.8.3/lavasrc-plugin-4.8.3.jar /opt/Lavalink/plugins/
# Small heap + SerialGC: a handful of players fits easily in 256 MB, and SerialGC has far less memory/thread
# overhead than G1 (pauses on a heap this size are a few ms). C1-only JIT boots faster and uses less CPU/RAM.
# Override with a Railway variable if needed.
ENV _JAVA_OPTIONS="-Xmx256m -Xss512k -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:MaxMetaspaceSize=128m -XX:ReservedCodeCacheSize=48m"
EXPOSE 2333
