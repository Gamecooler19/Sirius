# Bakes pgbouncer.ini and userlist.txt into the image so no running
# container reads a host path.
FROM edoburu/pgbouncer:latest
COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY userlist.txt /etc/pgbouncer/userlist.txt
