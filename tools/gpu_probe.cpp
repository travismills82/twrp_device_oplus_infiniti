/* SPDX-License-Identifier: Apache-2.0 */
// Diagnostic only: creates an off-screen context, draws a triangle, and checks
// pixels. It does not take DRM master, alter scanout, start services or load a
// kernel module. Run with an external timeout: vendor drivers are untrusted.
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <stdexcept>
#include <string>

template <typename T> T Symbol(void* library, const char* name) {
    void* result = dlsym(library, name);
    if (!result) throw std::runtime_error(std::string("Missing symbol: ") + name);
    return reinterpret_cast<T>(result);
}

std::string Escape(const char* input) {
    std::string result;
    for (const unsigned char ch : std::string(input ? input : "")) {
        if (ch == '"' || ch == '\\') result += '\\';
        if (ch >= 32 && ch < 127) result += static_cast<char>(ch);
    }
    return result;
}

int main(int argc, char** argv) {
    const char* egl_path = "libEGL.so";
    const char* gles_path = "libGLESv2.so";
    for (int arg = 1; arg < argc; ++arg) {
        if (arg + 1 < argc && !strcmp(argv[arg], "--egl")) egl_path = argv[++arg];
        else if (arg + 1 < argc && !strcmp(argv[arg], "--gles")) gles_path = argv[++arg];
        else { fprintf(stderr, "usage: twrp-gpu-probe [--egl LIB] [--gles LIB]\n"); return 64; }
    }
    try {
        void* egl = dlopen(egl_path, RTLD_NOW | RTLD_LOCAL);
        if (!egl) throw std::runtime_error(std::string("Cannot load EGL: ") + dlerror());
        void* gles = dlopen(gles_path, RTLD_NOW | RTLD_LOCAL);
        if (!gles) throw std::runtime_error(std::string("Cannot load GLES: ") + dlerror());
#define EGL_FUNCTION(name) auto name##Fn = Symbol<decltype(&name)>(egl, #name)
#define GL_FUNCTION(name) auto name##Fn = Symbol<decltype(&name)>(gles, #name)
        EGL_FUNCTION(eglGetDisplay); EGL_FUNCTION(eglInitialize);
        EGL_FUNCTION(eglChooseConfig); EGL_FUNCTION(eglBindAPI);
        EGL_FUNCTION(eglCreatePbufferSurface); EGL_FUNCTION(eglCreateContext);
        EGL_FUNCTION(eglMakeCurrent); EGL_FUNCTION(eglDestroyContext);
        EGL_FUNCTION(eglDestroySurface); EGL_FUNCTION(eglTerminate);
        EGL_FUNCTION(eglQueryString); EGL_FUNCTION(eglGetError);
        GL_FUNCTION(glGetString); GL_FUNCTION(glClearColor); GL_FUNCTION(glClear);
        GL_FUNCTION(glReadPixels); GL_FUNCTION(glGetError); GL_FUNCTION(glFinish);
        GL_FUNCTION(glCreateShader); GL_FUNCTION(glShaderSource); GL_FUNCTION(glCompileShader);
        GL_FUNCTION(glGetShaderiv); GL_FUNCTION(glCreateProgram); GL_FUNCTION(glAttachShader);
        GL_FUNCTION(glBindAttribLocation); GL_FUNCTION(glLinkProgram); GL_FUNCTION(glGetProgramiv);
        GL_FUNCTION(glUseProgram); GL_FUNCTION(glVertexAttribPointer);
        GL_FUNCTION(glEnableVertexAttribArray); GL_FUNCTION(glDrawArrays);
        GL_FUNCTION(glDeleteProgram); GL_FUNCTION(glDeleteShader); GL_FUNCTION(glViewport);
        EGLDisplay display = eglGetDisplayFn(EGL_DEFAULT_DISPLAY);
        EGLint major = 0, minor = 0;
        auto egl_check = [&](bool success, const char* operation) {
            if (success) return;
            char message[160];
            snprintf(message, sizeof(message), "%s failed: EGL error 0x%x", operation, eglGetErrorFn());
            throw std::runtime_error(message);
        };
        egl_check(display != EGL_NO_DISPLAY, "eglGetDisplay");
        egl_check(eglInitializeFn(display, &major, &minor), "eglInitialize");
        egl_check(eglBindAPIFn(EGL_OPENGL_ES_API), "eglBindAPI");
        const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
        EGLConfig config = nullptr;
        EGLint configs = 0;
        egl_check(eglChooseConfigFn(display, attributes, &config, 1, &configs) && configs == 1, "eglChooseConfig");
        const EGLint surface_size[] = {EGL_WIDTH, 32, EGL_HEIGHT, 32, EGL_NONE};
        const EGLSurface surface = eglCreatePbufferSurfaceFn(display, config, surface_size);
        egl_check(surface != EGL_NO_SURFACE, "eglCreatePbufferSurface");
        const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
        const EGLContext context = eglCreateContextFn(display, config, EGL_NO_CONTEXT, context_attributes);
        egl_check(context != EGL_NO_CONTEXT, "eglCreateContext");
        egl_check(eglMakeCurrentFn(display, surface, surface, context), "eglMakeCurrent");
        const std::string vendor = Escape(reinterpret_cast<const char*>(glGetStringFn(GL_VENDOR)));
        const std::string renderer = Escape(reinterpret_cast<const char*>(glGetStringFn(GL_RENDERER)));
        const std::string version = Escape(reinterpret_cast<const char*>(glGetStringFn(GL_VERSION)));
        const std::string egl_vendor = Escape(eglQueryStringFn(display, EGL_VENDOR));
        std::string lower = renderer;
        std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char ch) { return std::tolower(ch); });
        const bool hardware = lower.find("adreno") != std::string::npos &&
            lower.find("swiftshader") == std::string::npos && lower.find("llvmpipe") == std::string::npos;
        auto shader = [&](GLenum type, const char* text) {
            GLuint id = glCreateShaderFn(type);
            glShaderSourceFn(id, 1, &text, nullptr);
            glCompileShaderFn(id);
            GLint compiled = 0;
            glGetShaderivFn(id, GL_COMPILE_STATUS, &compiled);
            if (!compiled) throw std::runtime_error("GPU shader compilation failed");
            return id;
        };
        const GLuint vertex = shader(GL_VERTEX_SHADER, "attribute vec2 position; void main(){gl_Position=vec4(position,0.,1.);}");
        const GLuint fragment = shader(GL_FRAGMENT_SHADER, "precision mediump float; void main(){gl_FragColor=vec4(0.,1.,0.,1.);}");
        const GLuint program = glCreateProgramFn();
        glAttachShaderFn(program, vertex); glAttachShaderFn(program, fragment);
        glBindAttribLocationFn(program, 0, "position"); glLinkProgramFn(program);
        GLint linked = 0;
        glGetProgramivFn(program, GL_LINK_STATUS, &linked);
        if (!linked) throw std::runtime_error("GPU shader link failed");
        glViewportFn(0, 0, 32, 32);
        glClearColorFn(1, 0, 0, 1); glClearFn(GL_COLOR_BUFFER_BIT);
        glUseProgramFn(program);
        const GLfloat triangle[] = {-1,-1, 1,-1, -1,1};
        glVertexAttribPointerFn(0, 2, GL_FLOAT, GL_FALSE, 0, triangle);
        glEnableVertexAttribArrayFn(0); glDrawArraysFn(GL_TRIANGLES, 0, 3); glFinishFn();
        unsigned char inside[4] {}, outside[4] {};
        glReadPixelsFn(8, 8, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, inside);
        glReadPixelsFn(24, 24, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, outside);
        const bool pixels = glGetErrorFn() == GL_NO_ERROR && inside[0] < 8 && inside[1] > 247 &&
            inside[2] < 8 && outside[0] > 247 && outside[1] < 8 && outside[2] < 8;
        glDeleteProgramFn(program); glDeleteShaderFn(vertex); glDeleteShaderFn(fragment);
        eglMakeCurrentFn(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        eglDestroyContextFn(display, context); eglDestroySurfaceFn(display, surface); eglTerminateFn(display);
        printf("TWRP_GPU_PROBE {\"hardware\":%s,\"shader_readback\":%s,\"vendor\":\"%s\","
            "\"renderer\":\"%s\",\"version\":\"%s\",\"egl_vendor\":\"%s\",\"egl\":\"%d.%d\"}\n",
            hardware ? "true" : "false", pixels ? "true" : "false", vendor.c_str(), renderer.c_str(),
            version.c_str(), egl_vendor.c_str(), major, minor);
        return hardware && pixels ? 0 : 2;
    } catch (const std::exception& error) {
        fprintf(stderr, "TWRP_GPU_PROBE unavailable: %s\n", error.what());
        return 1;
    }
}
