ARG GAMDL_VERSION=2.9.2
ARG N_M3U8DL_RE_VERSION=v0.5.1-beta
ARG AMDECRYPT_VERSION=0.0.1
ARG BENTO4_VERSION=v1.6.0-641
ARG GPAC_VERSION=v2.4.0
ARG PYTHON_VERSION=3.12
ARG BASE_IMAGE=trixie

FROM mcr.microsoft.com/devcontainers/dotnet:dev-10.0 AS build-dotnet

ARG N_M3U8DL_RE_VERSION
ARG TARGETARCH

RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    clang-14

# N_m3u8DL-RE
WORKDIR /
RUN git clone https://github.com/nilaoda/N_m3u8DL-RE.git && \
    cd N_m3u8DL-RE && git checkout ${N_M3U8DL_RE_VERSION}
WORKDIR /N_m3u8DL-RE
RUN dotnet publish src/N_m3u8DL-RE \
    -r linux-${TARGETARCH} \
    -c Release \
    -p:StripSymbols=true \
    -p:CppCompilerAndLinker=clang-14 \
    -o /usr/local/bin

FROM mcr.microsoft.com/devcontainers/go:2.0.5-1.25-bookworm AS build-go

ARG AMDECRYPT_VERSION

# amdecrypt
WORKDIR /
RUN git clone https://github.com/glomatico/amdecrypt.git && \
    cd amdecrypt && git checkout ${AMDECRYPT_VERSION}
WORKDIR /amdecrypt
RUN go mod tidy
RUN go build -o /usr/local/bin/amdecrypt main.go

FROM mcr.microsoft.com/devcontainers/python:dev-3.12 AS build-python

ARG BENTO4_VERSION
ARG GPAC_VERSION

RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    cmake

# mp4decrypt
WORKDIR /
RUN git clone https://github.com/axiomatic-systems/Bento4.git && \
    cd Bento4 && git checkout ${BENTO4_VERSION}
WORKDIR /Bento4
RUN mkdir cmakebuild
WORKDIR /Bento4/cmakebuild
RUN cmake -DCMAKE_BUILD_TYPE=Release ..
RUN make
RUN make install

# mp4box
WORKDIR /
RUN git clone https://github.com/gpac/gpac.git && \
    cd gpac && git checkout ${GPAC_VERSION}
WORKDIR /gpac
RUN ./configure --static-mp4box
RUN make -j$(nproc)
RUN make install

FROM mcr.microsoft.com/devcontainers/python:dev-3.12
COPY --from=build-dotnet /usr/local/bin/N_m3u8DL-RE /usr/local/bin/
COPY --from=build-go /usr/local/bin/amdecrypt /usr/local/bin
COPY --from=build-python /usr/local/bin/mp4decrypt /usr/local/bin/
COPY --from=build-python /usr/local/bin/MP4Box /usr/local/bin/
