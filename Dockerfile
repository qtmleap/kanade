# syntax=docker/dockerfile:1
# ============================================================
# kanade — production multi-stage Dockerfile
# ============================================================
#
# Build:
#   docker buildx build -t kanade .
#
# Run (server mode):
#   docker run --rm -it \
#     -e REDIS_HOST=redis \
#     -v ./cookies.txt:/app/cookies.txt:ro \
#     -v ./config.ini:/app/config.ini:ro \
#     -p 5000:5000 \
#     kanade serve
# ============================================================

ARG PYTHON_VERSION=3.12
ARG DOTNET_VERSION=10.0

# ------------------------------------------------------------------
# Stage 1: Build N_m3u8DL-RE (.NET AOT)
# ------------------------------------------------------------------
FROM mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION} AS build-n_m3u8dl

ARG TARGETARCH

RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git clang

RUN git clone https://github.com/nilaoda/N_m3u8DL-RE.git --depth 1 /src

WORKDIR /src

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
    -p:InvariantGlobalization=true \
    -o /out

# ------------------------------------------------------------------
# Stage 2: Build amdecrypt (Go)
# ------------------------------------------------------------------
FROM golang:1.23-bookworm AS build-amdecrypt

RUN git clone https://github.com/glomatico/amdecrypt.git --depth 1 /src

WORKDIR /src

RUN go mod tidy && go build -o /out/amdecrypt main.go

# ------------------------------------------------------------------
# Stage 3: Build mp4decrypt (Bento4)
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS build-bento4

RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git cmake g++ make

RUN git clone https://github.com/axiomatic-systems/Bento4.git --depth 1 /src

WORKDIR /src/cmakebuild

RUN cmake -DCMAKE_BUILD_TYPE=Release .. && \
    make -j"$(nproc)" && \
    make install

# ------------------------------------------------------------------
# Stage 4: Build MP4Box (GPAC)
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS build-gpac

RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git build-essential zlib1g-dev

RUN git clone https://github.com/gpac/gpac.git --depth 1 /src

WORKDIR /src

RUN ./configure --static-bin && \
    make -j"$(nproc)" && \
    make install

# ------------------------------------------------------------------
# Stage 5: Install Python dependencies
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS build-python

WORKDIR /build

COPY pyproject.toml ./

RUN \
    --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install .

# ------------------------------------------------------------------
# Stage 6: Final runtime image
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim

# ffmpeg is needed by gamdl / yt-dlp for remuxing
RUN \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg

# Binaries from build stages
COPY --from=build-n_m3u8dl  /out/N_m3u8DL-RE          /usr/local/bin/
COPY --from=build-amdecrypt /out/amdecrypt             /usr/local/bin/
COPY --from=build-bento4    /usr/local/bin/mp4decrypt   /usr/local/bin/
COPY --from=build-gpac      /usr/local/bin/MP4Box       /usr/local/bin/

# Python packages
COPY --from=build-python /install /usr/local

# Application
WORKDIR /app
COPY main.py ./
COPY kanade/ ./kanade/

# N_m3u8DL-RE writes logs here
RUN mkdir -p /usr/local/bin/Logs && chmod 777 /usr/local/bin/Logs

# Default mount point for downloaded content
VOLUME ["/app/content"]

ENV ENV=production

# Server mode port (Flask / gunicorn)
EXPOSE 5000

ENTRYPOINT ["python", "main.py"]
CMD ["serve"]
