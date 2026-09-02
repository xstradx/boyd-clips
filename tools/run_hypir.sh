cd /d/AI-Models/HYPIR
export PYTHONPATH="D:/AI-Models/pylibs;D:/AI-Models/HYPIR"
LM="to_k,to_q,to_v,to_out.0,conv,conv1,conv2,conv_shortcut,conv_out,proj_in,proj_out,ff.net.2,ff.net.0.proj"
"C:/Users/natha/AI-Tools/Fooocus/venv/Scripts/python.exe" test.py \
  --base_model_type sd2 \
  --base_model_path Manojb/stable-diffusion-2-1-base \
  --model_t 200 --coeff_t 200 --lora_rank 256 --lora_modules "$LM" \
  --weight_path weights/HYPIR_sd2.pth \
  --patch_size 512 --stride 256 \
  --lq_dir in --scale_by factor --upscale 4 \
  --captioner fixed --fixed_caption "two men standing in a courtroom, one in an orange jail uniform, one in a suit, sharp clear photograph" \
  --output_dir out
