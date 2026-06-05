ARG GAMDL_VERSION=2.9.2
ARG N_M3U8DL_RE_VERSION=v0.5.1-beta
ARG AMDECRYPT_VERSION=0.0.1
ARG BENTO4_VERSION=v1.6.0-641
ARG GPAC_VERSION=v2.4.0
ARG PYTHON_VERSION=3.12
ARG BASE_IMAGE=trixie

FROM dhi.io/dotnet:10-sdk AS build-dotnet

ARG N_M3U8DL_RE_VERSION
ARG TARGETARCH

# pinning apt versions across rolling Debian bases is unmaintainable
# hadolint ignore=DL3008
RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    clang \
    git

# N_m3u8DL-RE
WORKDIR /
RUN git clone https://github.com/nilaoda/N_m3u8DL-RE.git --depth 1
WORKDIR /N_m3u8DL-RE
# Fix C# 14 breaking change: 'this' not allowed in nameof() in attributes
RUN sed -i 's/nameof(this\.\([a-zA-Z]*\))/nameof(\1)/g' \
    src/N_m3u8DL-RE.Parser/StreamExtractor.cs
RUN \
    --mount=type=cache,target=/root/.nuget/packages \
    case "${TARGETARCH}" in \
    arm64) RID="linux-arm64" ;; \
    amd64) RID="linux-x64"  ;; \
    *)     echo "Unsupported arch: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    dotnet publish src/N_m3u8DL-RE \
    -r "${RID}" \
    -c Release \
    -p:StripSymbols=true \
    -p:CppCompilerAndLinker=clang \
    -o /usr/local/bin

FROM mcr.microsoft.com/devcontainers/go:2.0.5-1.25-bookworm AS build-go

ARG AMDECRYPT_VERSION

# amdecrypt
WORKDIR /amdecrypt
RUN git clone https://github.com/glomatico/amdecrypt.git . && \
    git checkout ${AMDECRYPT_VERSION} && \
    go mod tidy && \
    go build -o /usr/local/bin/amdecrypt main.go

FROM mcr.microsoft.com/devcontainers/python:dev-3.12 AS build-python

ARG BENTO4_VERSION
ARG GPAC_VERSION

# pinning apt versions across rolling Debian bases is unmaintainable
# hadolint ignore=DL3008
RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    cmake

# mp4decrypt
WORKDIR /Bento4
RUN git clone https://github.com/axiomatic-systems/Bento4.git . && \
    git checkout ${BENTO4_VERSION}
WORKDIR /Bento4/cmakebuild
RUN cmake -DCMAKE_BUILD_TYPE=Release .. && \
    make && \
    make install

# mp4box
WORKDIR /gpac
RUN git clone https://github.com/gpac/gpac.git . && \
    git checkout ${GPAC_VERSION} && \
    ./configure --static-mp4box && \
    make -j"$(nproc)" && \
    make install

FROM mcr.microsoft.com/devcontainers/python:dev-3.12
COPY --from=build-dotnet /usr/local/bin/N_m3u8DL-RE /usr/local/bin/
COPY --from=build-go /usr/local/bin/amdecrypt /usr/local/bin
COPY --from=build-python /usr/local/bin/mp4decrypt /usr/local/bin/
COPY --from=build-python /usr/local/bin/MP4Box /usr/local/bin/
