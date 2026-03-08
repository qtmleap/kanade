import subprocess


def run_gamdl(url: str):
    """gamdl を実行し、出力を行単位で yield するジェネレータを返す。

    最後に returncode を返す。非ゼロの場合は CalledProcessError を送出。
    """
    proc = subprocess.Popen(
        ["gamdl", "--config-path", "config.ini", url],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in proc.stdout:
        yield line.rstrip("\n")

    proc.wait()

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)
