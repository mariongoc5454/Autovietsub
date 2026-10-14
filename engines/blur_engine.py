class BlurEngine:
    @staticmethod
    def build_blur_filter(blur_y_ratio, blur_strength, blur_height_ratio):
        blur_height_expr = f"(ih*{blur_height_ratio})"
        khoang_cach = f"({blur_height_expr}/2)"
        
        toa_do_cat_y = f"max(0\\,min(ih*{blur_y_ratio}-{khoang_cach}\\,ih-{blur_height_expr}))"
        
        # Trong bộ lọc overlay, chiều cao video gốc là H, chiều cao ảnh ghép vào là h
        # Không được dùng ih ở đây vì overlay không định nghĩa biến ih
        toa_do_ghep_y = f"max(0\\,min(H*{blur_y_ratio}-(h/2)\\,H-h))"
        
        bo_loc_mo = (
            f"split=2[bg][blur_src];"
            f"[blur_src]crop=w=iw:h={blur_height_expr}:x=0:y={toa_do_cat_y},gblur=sigma={blur_strength}[blur_out];"
            f"[bg][blur_out]overlay=x=0:y={toa_do_ghep_y}"
        )
        return bo_loc_mo

    @staticmethod
    def apply_logo_blur(base_filter, size_percent):
        kich_thuoc = f"ih*{size_percent/100}"
        
        # Tách riêng tọa độ cắt (dùng ih) và tọa độ ghép (dùng H)
        vi_tri_cat = f"ih*0.03"
        vi_tri_ghep = f"H*0.03"
        
        bo_loc_logo = (
            f"split=2[nen_logo][nguon_logo];"
            f"[nguon_logo]crop=w={kich_thuoc}:h={kich_thuoc}:x={vi_tri_cat}:y={vi_tri_cat}[logo_cat];"
            
            f"[logo_cat]split=3[logo_goc][logo_lam_mo][logo_mat_na];"
            
            f"[logo_lam_mo]gblur=sigma=15[logo_da_mo];"
            
            f"[logo_mat_na]format=gray,geq=lum='255*lt((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2)\\,W*W/4)'[mat_na_tron];"
            
            f"[logo_goc][logo_da_mo][mat_na_tron]maskedmerge[logo_hinh_tron];"
            f"[nen_logo][logo_hinh_tron]overlay=x={vi_tri_ghep}:y={vi_tri_ghep}"
        )
        return f"{bo_loc_logo}[sau_khi_xoa_logo];[sau_khi_xoa_logo]{base_filter}"

    @staticmethod
    def apply_blur(base_filter, blur_enabled, blur_y_ratio, blur_strength, blur_height, logo_blur_enabled, logo_size_percent):
        bo_loc_hien_tai = base_filter
        
        if blur_enabled:
            bo_loc_duoi = BlurEngine.build_blur_filter(blur_y_ratio, blur_strength, blur_height)
            bo_loc_hien_tai = f"{bo_loc_duoi}[truoc_khi_chen_sub];[truoc_khi_chen_sub]{bo_loc_hien_tai}"
            
        if logo_blur_enabled:
            bo_loc_hien_tai = BlurEngine.apply_logo_blur(bo_loc_hien_tai, logo_size_percent)
            
        return bo_loc_hien_tai