ARG BUILD_FROM
FROM $BUILD_FROM

#ARG BUILD_ARCH
#ARG CONFIGURATOR_VERSION


# Install requirements for add-on
RUN apk add --no-cache --virtual .build-deps \
    py3-pip \
    python3 \
    && pip3 install \
    paho-mqtt \
	pyserial

LABEL Description="Heatmiser Thermostats"

# Copy data for add-on
COPY data/ heatmiser

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]