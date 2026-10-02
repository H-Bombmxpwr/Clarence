# Lavalink server for Clarence. Deploy this folder as its own Railway service.
FROM ghcr.io/lavalink-devs/lavalink:4.2.2
COPY application.yml /opt/Lavalink/application.yml
# Fixed heap + short GC pauses so garbage collection doesn't stall audio. Override with a Railway variable if needed.
ENV _JAVA_OPTIONS="-Xmx512m -XX:+UseG1GC -XX:MaxGCPauseMillis=50"
EXPOSE 2333
