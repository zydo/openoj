ARG NODE_VERSION="22.23.2"
ARG PYTHON_VERSION="3.14.7"
ARG TYPESCRIPT_VERSION="7.0.2"

FROM node:${NODE_VERSION}-bookworm-slim AS typescript-toolchain

ARG TYPESCRIPT_VERSION
RUN npm install --global --ignore-scripts --no-audit --no-fund \
    typescript@"${TYPESCRIPT_VERSION}"

FROM python:${PYTHON_VERSION}-slim

ARG GXX_PACKAGE_VERSION="4:14.2.0-1"
ARG GXX_TOOLCHAIN_PACKAGE_VERSION="14.2.0-19"
ARG GO_PACKAGE_VERSION="2:1.24~2"
ARG GO_TOOLCHAIN_PACKAGE_VERSION="1.24.4-1"
ARG GO_STDLIB_PACKAGE_VERSION="1.24.4-1"
ARG JDK_PACKAGE_VERSION="21.0.12+8-1~deb13u1"
ARG LIBCAP_PACKAGE_VERSION="1:2.75-10+deb13u1+b1"
ARG RUST_PACKAGE_VERSION="1.85.0+dfsg3-1"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /runner
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        g++="${GXX_PACKAGE_VERSION}" \
        g++-14="${GXX_TOOLCHAIN_PACKAGE_VERSION}" \
        golang-go="${GO_PACKAGE_VERSION}" \
        golang-1.24-go="${GO_TOOLCHAIN_PACKAGE_VERSION}" \
        golang-1.24-src="${GO_STDLIB_PACKAGE_VERSION}" \
        libcap2-bin="${LIBCAP_PACKAGE_VERSION}" \
        openjdk-21-jdk-headless="${JDK_PACKAGE_VERSION}" \
        rustc="${RUST_PACKAGE_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
COPY --from=typescript-toolchain /usr/local/bin/node /usr/local/bin/node
COPY --from=typescript-toolchain \
    /usr/local/lib/node_modules/typescript \
    /usr/local/lib/node_modules/typescript
RUN ln -s /usr/local/lib/node_modules/typescript/bin/tsc /usr/local/bin/tsc
COPY worker.py python_harness.py sql_harness.py leetcode_types.py privileges.py interactive_oracles.py ./
COPY compiler_sandbox.py runtime_sandbox.py ./
COPY executors ./executors
COPY java ./java
COPY benchmarks ./benchmark-sources
RUN mkdir -p /runner/java-classes /runner/benchmarks \
    && javac \
        -proc:none \
        -encoding UTF-8 \
        -g:none \
        -d /runner/java-classes \
        /runner/java/OpenOJJavaHarness.java \
        /runner/java/ListNode.java \
        /runner/java/TreeNode.java \
        /runner/java/GridMaster.java \
        /runner/java/InteractiveOracles.java
RUN g++ -std=c++20 -O2 \
        -o /runner/benchmarks/cpp /runner/benchmark-sources/benchmark.cpp \
    && go build -trimpath \
        -o /runner/benchmarks/go /runner/benchmark-sources/benchmark.go \
    && rustc --edition=2021 -C opt-level=2 -C debuginfo=0 \
        -o /runner/benchmarks/rust /runner/benchmark-sources/benchmark.rs \
    && cp /runner/benchmark-sources/typescript.js \
        /runner/benchmarks/typescript.js \
    && cp /runner/benchmark-sources/javascript.js \
        /runner/benchmarks/javascript.js \
    && rm -rf /runner/benchmark-sources /root/.cache/go-build
RUN groupadd --gid 10001 openoj \
    && useradd --uid 10000 --gid openoj --no-create-home openoj-runner \
    && cp /usr/local/bin/python3.14 /usr/local/bin/openoj-supervisor-python \
    && setcap cap_chown,cap_dac_override,cap_kill,cap_setuid,cap_setgid=ep \
        /usr/local/bin/openoj-supervisor-python \
    && mkdir -p /queue \
    && chown openoj-runner:openoj /queue \
    && chmod 0770 /queue \
    && chmod -R 0555 /runner

# The supervisor is unprivileged but retains five explicit container
# capabilities so it can manage and remove scratch space, drop children to
# UID/GID 65534, and terminate processes hostile submissions leave behind.
USER 10000:10001
CMD ["openoj-supervisor-python", "-I", "-S", "/runner/worker.py"]
