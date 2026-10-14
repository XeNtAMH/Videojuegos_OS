from getpass import getpass
from pathlib import Path
from datetime import datetime

import boto3


def main():
    endpoint_url = input("Endpoint S3 de Supabase: ").strip()
    region_name = input("Región S3: ").strip()
    bucket_name = input("Nombre del bucket: ").strip()
    access_key_id = getpass("Access key ID de Supabase Storage: ")
    secret_access_key = getpass("Secret access key de Supabase Storage: ")

    if not all((endpoint_url, region_name, bucket_name, access_key_id, secret_access_key)):
        raise ValueError("Todos los datos de conexión al bucket son obligatorios.")

    backup_root = (
        Path.home()
        / "Documents"
        / "VideoG_TO-backups"
        / f"storage_{datetime.now():%Y-%m-%d_%H-%M-%S}"
    )
    backup_root.mkdir(parents=True, exist_ok=False)

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )
    paginator = client.get_paginator("list_objects_v2")
    object_count = 0
    total_bytes = 0

    for page in paginator.paginate(Bucket=bucket_name):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith("/"):
                continue
            destination = backup_root.joinpath(*key.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket_name, key, str(destination))
            object_count += 1
            total_bytes += item["Size"]

    print(f"Objetos descargados: {object_count}")
    print(f"Tamaño total: {total_bytes} bytes")
    print(f"Respaldo creado: {backup_root}")


if __name__ == "__main__":
    main()
