import copy
import os.path

from lib.console import Console
from PIL import Image

from lib.sc import *
from lib.fla import *

import re
import json

shape_bitmaps_uvs = []
shape_bitmaps_twips = []
shapes_with_nine_slices = {}


def sc_to_fla(filepath):
    swf = SupercellSWF()
    swf.load(filepath)
    projectdir = os.path.splitext(swf.filename)[0]

    to_skip = []
    to_split = []

    blacklist = json.loads(open("blacklist.json", "r").read())

    for skip_condition in blacklist['skip']:
        if (isinstance(skip_condition, str)):
            to_skip.append(skip_condition)
        elif (isinstance(skip_condition, dict)):
            for key, array in skip_condition.items():
                if key == os.path.basename(swf.filename):
                    to_skip.extend(array)

    for split_condition in blacklist['split']:
        if (isinstance(split_condition, str)):
            to_split.append(split_condition)
        elif (isinstance(split_condition, dict)):
            for key, array in split_condition.items():
                if key == os.path.basename(swf.filename):
                    to_split.extend(array)

    flas = {}

    resource_counter = 0

    for resource_idx, (id, exports) in enumerate(swf.exports.items()):
        Console.progress_bar("Converting SupercellFlash resources to Adobe Animate...", resource_idx,
                             len(swf.exports.keys()))

        resource = swf.resources[id]

        if isinstance(resource, MovieClip):
            convert_movieclip(flas, swf, id, resource, projectdir, exports, to_skip, to_split)
        else:
            continue

        resource_counter += 1

    print()

    for fla in flas.values():
        Console.info(f"Saving a {fla.filepath}.fla")
        XFL.save(fla)


def prepare_document(path, framerate = 30):
    fla = DOMDocument(path)

    fla.xfl_version = 2.971

    fla.width = 1280
    fla.height = 720
    fla.frame_rate = framerate
    fla.current_timeline = 1

    fla.background_color = 0x666666

    fla.creator_info = "File generated with SC tool by SCW Make! (VK: vk.com/scwmake, GITHUB: github.com/scwmake/SC)"

    fla.folders.add(DOMFolderItem("shapes"))
    fla.folders.add(DOMFolderItem("movieclips"))
    fla.folders.add(DOMFolderItem("exports"))
    fla.folders.add(DOMFolderItem("resources"))

    startup = DOMDocument("lib/scwmake_credit")
    startup.load()

    fla.timelines = startup.timelines

    return fla

def convert_shape(fla, swf, id, shape):
    graphic = DOMSymbolItem(f"shapes/shape_{id}", "graphic")
    graphic.timeline.name = f"shape_{id}"

    for bitmap_index, bitmap in enumerate(reversed(shape.bitmaps)):
        layer = DOMLayer(f"shape_layer_{bitmap_index}", False)
        frame = DOMFrame(index=0)

        uv_coords = bitmap.uv_coords
        xy_coords = bitmap.xy_coords

        if uv_coords.count(uv_coords[0]) == len(uv_coords):  # color fills is always 1x1
            color_fill = DOMShape()
            texture = swf.textures[bitmap.texture_index]
            image = texture.get_image()

            x, y = uv_coords[0]
            pixel = image.getpixel((int(x), int(y)))

            color = 0
            alpha = 1.0

            if len(pixel) in (4, 3):
                color |= pixel[0] << 16
                color |= (pixel[1] << 16) >> 8
                color |= pixel[2]

                if len(pixel) == 4:
                    alpha = pixel[3] / 255

            elif len(pixel) in (2, 1):
                color |= pixel[0] << 16
                color |= (pixel[0] << 16) >> 8
                color |= pixel[0]

                if len(pixel) == 2:
                    alpha = pixel[1] / 255

            color_fill_style = FillStyle(1)
            color_fill_style.data = SolidColor(color, alpha)

            final_edges = ""
            for x, curr in enumerate(xy_coords):
                nxt = xy_coords[(x + 1) % len(xy_coords)]
                final_edges += f"!{curr[0] * 20} {curr[1] * 20}|{nxt[0] * 20} {nxt[1] * 20}"  # converting pixels to twips

            color_fill_edge = Edge()
            color_fill_edge.edges = final_edges
            color_fill_edge.fill_style1 = 1

            color_fill.fills.append(color_fill_style)
            color_fill.edges.append(color_fill_edge)

            frame.elements.append(color_fill)

        else:
            rotation = 0
            mirror = False

            if uv_coords not in shape_bitmaps_uvs:
                shape_bitmaps_uvs.append(uv_coords)

                matrix, twips, rotation, mirror = bitmap.get_matrix(use_nearest=True)
                shape_bitmaps_twips.append(twips)

            else:
                matrix, _, _, _ = bitmap.get_matrix(shape_bitmaps_twips[shape_bitmaps_uvs.index(uv_coords)])

            uvs_index = shape_bitmaps_uvs.index(uv_coords)

            bitmap_item_name =f"resources/{uvs_index}"

            if bitmap_item_name not in fla.media:
                bitmap_item = DOMBitmapItem(bitmap_item_name, f"M {uvs_index}.dat")

                bitmap_item.quality = 100
                bitmap_item.use_imported_jpeg_data = False
                texture: SWFTexture = swf.textures[bitmap.texture_index]
                bitmap_item.allow_smoothing = [texture.min_filter, texture.mag_filter] == ["GL_NEAREST", "GL_NEAREST"]
                bitmap_item.source_external_filepath = f"LIBRARY/resources/{uvs_index}.png"

                sprite = bitmap.get_image(swf)
                sprite = sprite.rotate(-rotation, expand=True)
                if mirror:
                    sprite = sprite.transpose(Image.FLIP_LEFT_RIGHT)
                bitmap_item.image = sprite

                fla.media[uvs_index] = bitmap_item

            bitmap_instance = DOMBitmapInstance()
            bitmap_instance.library_item_name = bitmap_item_name

            a, c, b, d, tx, ty = matrix.params
            bitmap_instance.matrix = Matrix(a, b, c, d, tx, ty)

            frame.elements.append(bitmap_instance)

        layer.frames.append(frame)
        graphic.timeline.layers.append(layer)

    fla.symbols.add(graphic.name, graphic)


def patch_shape_nine_slice(fla, id, shape):
    shape_slice = DOMGroup()

    shape_symbol = fla.symbols.get(f"shapes/shape_{id}")

    for l, layer in enumerate(shape_symbol.timeline.layers):
        for f, frame in enumerate(layer.frames):
            for e, element in enumerate(frame.elements):
                if isinstance(element, DOMBitmapInstance):
                    element_media = fla.media[int(element.library_item_name.split("/")[1])]
                    element_sprite = element_media.image
                    w, h = element_sprite.size

                    extrude_sprite = element_sprite.resize((w + 2, h + 2))
                    extrude_sprite.paste(element_sprite, (1, 1))
                    element_media.image = extrude_sprite

                    sprite_twip = [[0, 0], [w, 0], [w, h], [0, h]]

                    slice = DOMShape()
                    slice.is_drawing_object = True

                    edge_shape = ""
                    for x, curr in enumerate(sprite_twip):
                        nxt = sprite_twip[(x + 1) % len(sprite_twip)]
                        edge_shape += f"!{round(curr[0] * 20)} {round(curr[1] * 20)}|{round(nxt[0] * 20)} {round(nxt[1] * 20)}"

                    slice_style = FillStyle(1)
                    slice_bitmap_fill = BitmapFill(element.library_item_name)
                    slice_bitmap_fill.matrix = Matrix(20, 0, 0, 20, -1, -1)
                    slice_style.data = slice_bitmap_fill

                    slice_shape = Edge()
                    slice_shape.edges = edge_shape
                    slice_shape.fill_style1 = 1

                    slice.fills.append(slice_style)
                    slice.edges.append(slice_shape)
                    slice.matrix = element.matrix

                    shape_slice.members.append(slice)

                    shape_symbol.timeline.layers[l].frames[f].elements[e] = slice

    shapes_with_nine_slices[id] = shape_slice
    return shape_slice


def convert_movieclip(flas, swf, id, movieclip: MovieClip, projectdir, export_names: list = None, skip_list: list = [], split_list: list = []):
    if skip_list and False not in [re.match(block_name, export) != None for block_name in skip_list for export in export_names]:
        return

    if isinstance(flas, dict):
        fla_key = movieclip.frame_rate
        if export_names:
            for export in export_names:
                for split_name in split_list:
                    if re.match(split_name, export):
                        postfix = re.sub('[^\w_.)( -]', '', split_name)
                        fla_key = f"{fla_key}_{postfix}"
                else:
                    continue

                break

        if fla_key not in flas:
            flas[fla_key] = prepare_document(f'{projectdir}_{fla_key}', movieclip.frame_rate)

        fla = flas[fla_key]

    else:
        fla = flas

    movie = DOMSymbolItem()

    layers_instance = []
    layers_order = []
    symbols_instance = []

    masked_layers = {}
    masked_layers_order = {}

    # Prepearing layers
    for i, bind in enumerate(movieclip.binds):
        bind_resource = swf.resources[bind['id']]
        if isinstance(bind_resource, MovieClipModifier):
            layers_instance.append(None)
            symbols_instance.append(bind_resource)
        else:
            # Layers
            bind_layer = DOMLayer(f"Layer_{i}")
            if bind["name"]:
                bind_layer.name = bind["name"]

            # Layer order
            layers_order.append(i)

            # Symbols instance
            if isinstance(bind_resource, Shape):
                if f"shapes/shape_{bind['id']}" not in fla.symbols:
                    convert_shape(fla, swf, bind['id'], bind_resource)
                if movieclip.nine_slice:
                    if id in shapes_with_nine_slices:
                        bind_instance = shapes_with_nine_slices[id]
                    else:
                        bind_instance = patch_shape_nine_slice(fla, bind['id'], bind_resource)

                else:
                    bind_instance = DOMSymbolInstance(library_item_name=f"shapes/shape_{bind['id']}")

            elif isinstance(bind_resource, MovieClip):
                if f"movieclips/movieclip_{bind['id']}" not in fla.symbols:
                    convert_movieclip(fla, swf, bind["id"], bind_resource, projectdir= projectdir)

                bind_instance = DOMSymbolInstance(name=bind["name"],
                                                library_item_name=f"movieclips/movieclip_{bind['id']}")
                bind_instance.blend_mode = bind['blend']



            elif isinstance(bind_resource, TextField):
                bind_instance = DOMDynamicText(name=bind["name"])

                bind_instance.width = bind_resource.left_corner - bind_resource.top_corner
                bind_instance.height = bind_resource.right_corner - bind_resource.bottom_corner
                bind_instance.top = bind_resource.bottom_corner
                bind_instance.left = bind_resource.top_corner

                if bind_resource.multiline:
                    bind_instance.line_type = "multiline no wrap"

                text_run = DOMTextRun()
                text_attrs = DOMTextAttrs()

                if bind_resource.font_align == 18: #TODO: still idk what is it
                    text_attrs.alignment = "center"

                if bind_resource.text is not None:
                    text_run.characters = bind_resource.text

                text_attrs.face = bind_resource.font_name
                text_attrs.size = bind_resource.font_size
                text_attrs.bitmap_size = bind_resource.font_size * 20

                if bind_resource.bold or bind_resource.italic:
                    text_attrs.face += "-"

                if bind_resource.bold:
                    text_attrs.face += "Bold"

                if bind_resource.italic:
                    text_attrs.face += "Italic"

                text_attrs.fill_color = bind_resource.font_color & 0xFFFFFF00
                text_attrs.alpha = (bind_resource.font_color & 0x000000FF) / 255

                if bind_resource.outline_color:
                    glow_filter = GlowFilter()

                    glow_filter.blur_x = 2
                    glow_filter.blur_y = 2

                    glow_filter.color = bind_resource.outline_color & 0xFFFFFF00

                    glow_filter.strength = 15

                    if bind_resource.c1:
                        glow_filter.strength = bind_resource.c1 / 65535

                    bind_instance.filters.append(glow_filter)

                if bind_resource.c2:
                    drop_shadow_filter = DrowShadowFilter()

                    drop_shadow_filter.angle = (bind_resource.c2 / 65535) * 360

                    drop_shadow_filter.blur_x = 4
                    drop_shadow_filter.blur_y = 4

                    drop_shadow_filter.distance = 4

                    bind_instance.filters.append(drop_shadow_filter)

                text_run.text_attrs.append(text_attrs)

                bind_instance.text_runs.append(text_run)

            else:
                print("Unkwnown resource type")
                raise TypeError()

            symbols_instance.append(bind_instance)
            layers_instance.append(bind_layer)

    # Converting frames
    for i, frame in enumerate(movieclip.frames):
        elements = [element['bind'] for element in frame.elements]
        elements_idx = [element for element in elements if not isinstance(swf.resources[movieclip.binds[element]['id']], MovieClipModifier)]

        for element in elements_idx:
            for comparative in elements_idx:
                if comparative != element:
                    element_pos = elements_idx.index(element)
                    bind_pos = layers_order.index(element)

                    comparative_pos = elements_idx.index(comparative)
                    cmp_bind_pos = layers_order.index(comparative)

                    frame_position = element_pos > comparative_pos  # higher if True else lower
                    binds_position = bind_pos > cmp_bind_pos

                    if frame_position != binds_position:
                        layers_order.insert(layers_order.index(element), layers_order.pop(cmp_bind_pos))
        mask = False
        masked = False
        mask_layer = None
        for layer_idx, curr_layer in enumerate(layers_instance):
            if curr_layer is None:
                modifer = symbols_instance[layer_idx].modifier

                if modifer == modifer.Mask:
                    mask = True
                elif modifer == modifer.Masked:
                    mask = False
                    masked = True
                elif modifer == modifer.Unmasked:
                    masked = False
                    mask_layer = None

            else:
                if layer_idx in elements:
                    if mask:
                        curr_layer.layer_type = "mask"
                        curr_layer.is_locked = True
                        mask_layer = curr_layer
                    elif masked:
                        if mask_layer not in masked_layers:
                            masked_layers[mask_layer] = []
                            masked_layers_order[mask_layer] = []

                        if curr_layer not in masked_layers[mask_layer]:
                            masked_layers[mask_layer].append(curr_layer)
                            masked_layers_order[mask_layer].append(masked_layers[mask_layer].index(curr_layer))

                    element = frame.elements[elements.index(layer_idx)]

                    if curr_layer.frames and i:
                        if element in movieclip.frames[i-1].elements:
                            curr_layer.frames[-1].duration += 1
                            continue

                    layer_frame = DOMFrame(i)
                    instance = copy.deepcopy(symbols_instance[layer_idx])


                    if element["matrix"] != 0xFFFF:
                        m = swf.matrix_banks[movieclip.matrix_bank].matrices[element["matrix"]]
                        instance.matrix = Matrix(m.a, m.b, m.c, m.d, m.tx, m.ty)

                    if element["color"] != 0xFFFF:
                        c = swf.matrix_banks[movieclip.matrix_bank].color_transforms[element["color"]]
                        bind_color = Color()
                        bind_color.red_offset = c.r_add
                        bind_color.green_offset = c.g_add
                        bind_color.blue_offset = c.b_add
                        bind_color.alpha_offset = 0
                        bind_color.red_multiplier = c.r_mul
                        bind_color.green_multiplier = c.g_mul
                        bind_color.blue_multiplier = c.b_mul
                        bind_color.alpha_multiplier = c.a_mul
                        instance.color = bind_color

                    layer_frame.elements.append(instance)
                    curr_layer.frames.append(layer_frame)

                else:
                    if curr_layer.frames and len(curr_layer.frames[-1].elements) == 0:
                        curr_layer.frames[-1].duration += 1
                    else:
                        curr_layer.frames.append(DOMFrame(i))

    layers_order = [o for o in layers_order if
                    layers_instance[o] not in [masked_layers[order_key][value] for order_key, order_list in
                                               masked_layers_order.items() for value in order_list]]

    for idx in reversed(layers_order):
        movie.timeline.layers.append(layers_instance[idx])

    for layer_key in masked_layers_order:
        if layer_key is not None:
            for idx in masked_layers_order[layer_key]:
                mask_layer_index = movie.timeline.layers.index(layer_key)
                masked_layer = masked_layers[layer_key][idx]
                masked_layer.is_locked = True
                masked_layer.parent_layer_index = mask_layer_index
                movie.timeline.layers.insert(mask_layer_index + 1, masked_layer)

    if movieclip.nine_slice:
        x, y, width, height = movieclip.nine_slice

        movie.scale_grid_left = x
        movie.scale_grid_top = y
        movie.scale_grid_right = x + width
        movie.scale_grid_bottom = y + height

    if isinstance(export_names, list):
        for export in export_names:
            if not skip_list or True in [re.match(block_name, export) == None for block_name in skip_list]:
                movie_instance = copy.deepcopy(movie)
                movie_instance.name = f"exports/{export}"
                movie_instance.timeline.name = export
                fla.symbols.add(movie_instance.name, movie_instance)
        return

    movie.name = f"movieclips/movieclip_{id}"
    movie.timeline.name = f"movieclip_{id}"
    fla.symbols.add(movie.name, movie)
