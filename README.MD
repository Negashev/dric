# gric

Gitlab registry image cleaner

Recursive remove images by tag

without wait 200ok please (some images very big, and response is very long)

work with gitlab jwt ([Generate a token](https://docs.gitlab.com/ce/user/profile/personal_access_tokens.html) with `api` and `sudo` privileges)

```bash
docker run -it \
--name registry_cleaner \
--restart=always \
-d -p 8888:8888 \
-e CLEAN_TOKEN='mysecret key' \
-e REGISTRY_URL='https://registry.company' \
-e REGISTRY_LOGIN='login' \
-e REGISTRY_TOKEN='token or password' \
negash/dric python3 \
-m japronto run.app \
--worker-num 24 --port 8888
```

- remove tag recursive

    curl `/group/my-mono-repo/feature-123?clean-token=TOKEN`
    0000000000
    remove all images with tag `feature-123`
    
- remove unique image

    curl `/extra_path?clean-token=TOKEN&path=group/simple-repo/some_name:feature-123`
    
    remove one image with tag `feature-123`