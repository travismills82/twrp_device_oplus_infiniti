// SPDX-License-Identifier: GPL-3.0-or-later
// Compile against the real minuitwrp/truetype.cpp with ASan/UBSan on the host.
#include <linux/types.h>
#include "minuitwrp/truetype.hpp"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef TEST_BOLD_FONT
static unsigned Ink(TrueTypeFont* font, const char* label) {
    GGLSurface surface{};
    assert(twrpTruetype::gr_ttf_render_text(font, &surface, label, -1) ==
           static_cast<int>(strlen(label)));
    unsigned ink = 0;
    for (size_t i = 0; i < static_cast<size_t>(surface.stride) * surface.height; ++i)
        ink += surface.data[i];
    free(surface.data);
    return ink;
}

static void TestBoldFont(const char* filename) {
    auto* regular = static_cast<TrueTypeFont*>(twrpTruetype::gr_ttf_loadFont(filename, 32, 300));
    auto* bold = static_cast<TrueTypeFont*>(twrpTruetype::gr_ttf_loadFont(filename, 32, 300, true));
    assert(regular && bold && regular != bold);
    auto* same_bold = twrpTruetype::gr_ttf_loadFont(filename, 32, 300, true);
    assert(same_bold == bold);
    twrpTruetype::gr_ttf_freeFont(same_bold);
    const char* label = "DL 24.0  UL 99.9 MB/s";
    assert(Ink(bold, label) > Ink(regular, label));
    auto* scaled = static_cast<TrueTypeFont*>(twrpTruetype::gr_ttf_scaleFont(
        bold, 216, twrpTruetype::gr_ttf_measureEx(label, bold)));
    assert(scaled && scaled->size < bold->size && scaled->key->bold);
    auto* scaled_regular = static_cast<TrueTypeFont*>(
        twrpTruetype::gr_ttf_loadFont(filename, scaled->size, 300));
    assert(scaled_regular && scaled_regular != scaled && Ink(scaled, label) > Ink(scaled_regular, label));
    for (auto* font : {scaled_regular, scaled, bold, regular}) twrpTruetype::gr_ttf_freeFont(font);
    puts("Real minuitwrp bold weight, cache isolation and scaling PASS");
}
#endif

int main(int argc,char** argv) {
    if(argc!=3)return 64;
#ifdef TEST_BOLD_FONT
    TestBoldFont(argv[1]);
#endif
    for(int round=0;round<24;++round) {
        auto* font=static_cast<TrueTypeFont*>(twrpTruetype::gr_ttf_loadFont(argv[1],34+round%7,300));
        assert(font);
        auto* shared=static_cast<TrueTypeFont*>(twrpTruetype::gr_ttf_loadFont(argv[1],34+round%7,300));
        assert(shared==font && font->refcount==2);
        twrpTruetype::gr_ttf_freeFont(shared);
        assert(font->refcount==1);
        assert(twrpTruetype::gr_ttf_measureEx("CPU 34 \xc2\xb0" "C",font)>0);
        if(!strcmp(argv[2],"glyphs")) {
            for(const char* text : {"j","f","CPU 34 \xc2\xb0" "C","Swipe to Unlock","\xc3\x81\xc3\x89\xc3\xa7"}) {
                for(int width : {0,1,7,20,80,300,-1}) {
                    GGLSurface surface{};
                    (void)twrpTruetype::gr_ttf_render_text(font,&surface,text,width);
                    free(surface.data);
                }
            }
        }
        for(int n=0;n<450;++n) {
            const std::string label="CPU status "+std::to_string(n);
            assert(twrpTruetype::gr_ttf_measureEx(label.c_str(),font)>0);
        }
        twrpTruetype::gr_ttf_freeFont(font);
    }
    puts("Real minuitwrp font release/glyph bounds PASS");
}
