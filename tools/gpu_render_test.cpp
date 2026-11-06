/* SPDX-License-Identifier: Apache-2.0 */
// Off-screen compositor comparison only: never opens DRM or any block device.
#include <linux/types.h>
#include <cutils/properties.h>
#include <pixelflinger/pixelflinger.h>
#include "graphics_gles.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <csignal>
#include <fcntl.h>
#include <ucontext.h>
#include <unistd.h>
#include <vector>

int main(int argc, char** argv) {
    // Recovery may lack crash_dump64. Diagnostic-only maps, never user data.
    struct sigaction action{};
    action.sa_flags=SA_SIGINFO;
    action.sa_sigaction=[](int sig,siginfo_t*,void* raw) {
        auto* ctx=static_cast<ucontext_t*>(raw);
        dprintf(2,"GPU test signal=%d pc=%llx lr=%llx\n",sig,
            static_cast<unsigned long long>(ctx->uc_mcontext.pc),
            static_cast<unsigned long long>(ctx->uc_mcontext.regs[30]));
        int fd=open("/proc/self/maps",O_RDONLY|O_CLOEXEC);
        char buffer[4096]; ssize_t count;
        while(fd>=0 && (count=read(fd,buffer,sizeof(buffer)))>0) (void)write(2,buffer,count);
        if(fd>=0) close(fd);
        _exit(128+sig);
    };
    sigaction(SIGTRAP,&action,nullptr);
    setvbuf(stdout,nullptr,_IONBF,0);
    const bool benchmark=argc==2 && !strcmp(argv[1],"--benchmark");
    if(argc>1 && !benchmark) return 64;
    const int w=benchmark?1272:64, h=benchmark?2772:64, stride=benchmark?1280:72;
    std::vector<unsigned char> actual(stride*h*4, 0xcd), expected=actual;
    GRSurface target{w,h,stride*4,4,actual.data(),GGL_PIXEL_FORMAT_RGBA_8888};
    GGLSurface a{}, e{};
    a.version=e.version=sizeof(GGLSurface);
    a.width=e.width=w; a.height=e.height=h; a.stride=e.stride=stride;
    a.format=e.format=GGL_PIXEL_FORMAT_RGBA_8888;
    a.data=actual.data(); e.data=expected.data();
    GGLContext *cpu, *reference;
    gglInit(&cpu); gglInit(&reference);
    cpu->colorBuffer(cpu,&a); reference->colorBuffer(reference,&e);
    for (auto gl : {cpu,reference}) {
        gl->activeTexture(gl,0); gl->enable(gl,GGL_BLEND);
        gl->blendFunc(gl,GGL_SRC_ALPHA,GGL_ONE_MINUS_SRC_ALPHA);
    }
    gr_gpu_init(cpu,&target);
    auto color=[&](int r,int g,int b,int alpha) {
        gr_gpu_color(r,g,b,alpha);
        const GGLint values[]={r*257+1,g*257+1,b*257+1,alpha*257+1};
        cpu->color4xv(cpu,values); reference->color4xv(reference,values);
    };
    auto fill=[&](int x,int y,int rw,int rh,bool opaque) {
        if (!gr_gpu_fill(x,y,rw,rh)) { fprintf(stderr,"GPU fill did not initialize\n"); exit(1); }
        if (opaque) reference->disable(reference,GGL_BLEND);
        reference->recti(reference,x,y,x+rw,y+rh);
        reference->enable(reference,GGL_BLEND);
    };
    auto blit=[&](GGLSurface& image,int sx,int sy,int rw,int rh,int x,int y) {
        if (!gr_gpu_blit(&image,sx,sy,rw,rh,x,y)) { fprintf(stderr,"GPU blit unavailable\n"); exit(1); }
        if (image.format==GGL_PIXEL_FORMAT_RGBX_8888) reference->disable(reference,GGL_BLEND);
        reference->bindTexture(reference,&image);
        reference->texEnvi(reference,GGL_TEXTURE_ENV,GGL_TEXTURE_ENV_MODE,GGL_REPLACE);
        reference->texGeni(reference,GGL_S,GGL_TEXTURE_GEN_MODE,GGL_ONE_TO_ONE);
        reference->texGeni(reference,GGL_T,GGL_TEXTURE_GEN_MODE,GGL_ONE_TO_ONE);
        reference->enable(reference,GGL_TEXTURE_2D);
        reference->texCoord2i(reference,sx-x,sy-y);
        reference->recti(reference,x,y,x+rw,y+rh);
        reference->disable(reference,GGL_TEXTURE_2D); reference->enable(reference,GGL_BLEND);
    };
    auto compare=[&](const char* label) {
        int worst=0, bad=0;
        for(int y=0;y<h;++y) for(int x=0;x<stride;++x) for(int c=0;c<4;++c) {
            if(x<w && c==3) continue; // framebuffer alpha is not displayed
            size_t p=(y*stride+x)*4+c;
            int error=abs(int(actual[p])-int(expected[p]));
            worst=std::max(worst,error); if(error>2) ++bad;
        }
        printf("%s: max RGB/padding difference=%d, mismatches=%d\n",label,worst,bad);
        if(bad) exit(2);
    };
    color(20,40,60,255); fill(0,0,w,h,true);
    color(180,70,35,127); fill(3,5,21,18,false);
    gr_gpu_clip(10,12,25,19,true); reference->scissor(reference,10,12,25,19); reference->enable(reference,GGL_SCISSOR_TEST);
    color(30,170,220,255); fill(0,0,45,45,true);
    gr_gpu_clip(0,0,w,h,false); reference->disable(reference,GGL_SCISSOR_TEST);
    unsigned char rgba[]={255,0,0,255, 0,255,0,127, 0,0,255,0, 80,90,100,255};
    GGLSurface image{}; image.version=sizeof(image); image.width=image.height=image.stride=2;
    image.data=rgba; image.format=GGL_PIXEL_FORMAT_RGBA_8888;
    blit(image,0,0,2,2,40,20);
    image.format=GGL_PIXEL_FORMAT_RGBX_8888; blit(image,1,0,1,2,42,20);
    unsigned char mask[]={0,32,64,128, 192,224,255,0};
    image.width=image.stride=4; image.height=2; image.data=mask; image.format=GGL_PIXEL_FORMAT_A_8;
    color(230,180,90,180); blit(image,1,0,3,2,22,40);
    gr_gpu_flush(); compare("fills, alpha, clips, RGBA/RGBX, cropped A8 text and row stride");
    if (!property_get_bool("twrp.gpu.ready",false)) return 3;
    color(5,10,15,255); fill(48,48,8,8,true); gr_gpu_flush(); compare("persistent partial frame");
    gr_gpu_cpu_write(); actual[0]=expected[0]=99;
    color(100,110,120,255); fill(55,55,3,3,true); gr_gpu_flush(); compare("CPU line/snapshot synchronization");
    color(15,25,35,120); fill(2,2,12,13,false);
    char previous[PROPERTY_VALUE_MAX]; property_get("twrp.gpu.enable",previous,"1");
    property_set("twrp.gpu.enable","0"); gr_gpu_flush(); compare("pending-frame CPU fallback replay");
    property_set("twrp.gpu.enable",previous);
    if(benchmark) {
        constexpr int count=30;
        auto start=std::chrono::steady_clock::now();
        for(int frame=0;frame<count;++frame) {
            const GGLint solid[]={frame*257+1,40*257+1,60*257+1,65536};
            reference->color4xv(reference,solid); reference->disable(reference,GGL_BLEND);
            reference->recti(reference,0,0,w,h); reference->enable(reference,GGL_BLEND);
            for(int n=0;n<100;++n) reference->recti(reference,(n*31)%1100,(n*47)%2500,(n*31)%1100+100,(n*47)%2500+80);
        }
        auto middle=std::chrono::steady_clock::now();
        for(int frame=0;frame<count;++frame) {
            gr_gpu_color(frame,40,60,255);
            if(!gr_gpu_fill(0,0,w,h)) return 4;
            for(int n=0;n<100;++n) gr_gpu_fill((n*31)%1100,(n*47)%2500,100,80);
            gr_gpu_flush();
        }
        auto end=std::chrono::steady_clock::now();
        printf("1272x2772, %d frames, full fill +100 rectangles: CPU=%.2f ms/frame, GLES including readback=%.2f ms/frame\n",count,
            std::chrono::duration<double,std::milli>(middle-start).count()/count,
            std::chrono::duration<double,std::milli>(end-middle).count()/count);
    }
    gr_gpu_exit(); gglUninit(cpu); gglUninit(reference);
    printf("GPU compositor conformance PASS\n");
    return 0;
}
