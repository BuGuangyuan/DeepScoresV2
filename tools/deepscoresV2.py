from obb_anns import OBBAnns
from pathlib import Path
import sys
import os
from tqdm import tqdm
from PIL import Image
from images_display import ImageWall
from datetime import datetime
import keyboard


class DeepScoresV2:
    def __init__(self) -> None:
        self.__cats_anned = {}
        self.__allcats = {}

    def __assert_jsonfile(self, file):
        assert os.path.exists(file),f'{file}文件不存在'
        _, t = os.path.split(file)
        assert os.path.splitext(t)[1] in ['.json'], f"{t}不是json文件"   

    def __get_cats_info(self, annfiles, cats_bbox=True):
        cats = {}
        for f in annfiles:
            self.__assert_jsonfile(f)
            ob = OBBAnns(f)
            ob.load_annotations()
            ob.set_annotation_set_filter(['deepscores'])
            for k, v in ob.get_cats().items():
                cats.update({v['name']: 1})
        self.__allcats = cats
        if cats_bbox:
            for f in annfiles:
                images = os.path.join(os.path.split(f)[0], 'images')                
                ob = OBBAnns(f)
                ob.load_annotations()
                ob.set_annotation_set_filter(['deepscores'])            
                for i in tqdm(range(len(ob.img_info)), desc="处理中..."):
                    if len(cats):
                        filename = ob.img_info[i]['filename']
                        im = Image.open(Path(images).joinpath(filename))
                        df = ob.get_anns(i)
                        for j in range(len(df)):
                            ann =  df.iloc[j,]
                            name = ob.cat_info[df.iloc[j,]['cat_id'][0]]['name']
                            if cats.get(name):
                                regionn = ann['a_bbox']
                                im_cat = im.crop(regionn)
                                self.__cats_anned.update({name: im_cat})
                                cats.pop(name, "") 
                    else:
                        break

    def visualize_cats(self, *annfiles, mode='GRID', out=None, show=True):
        self.__get_cats_info(annfiles)
        if self.__cats_anned:
            if mode == 'GRID':
                columns = 10
                num = len(self.__cats_anned)
                lines = num // columns + 1 if num % columns else num // columns
                imw = ImageWall((200 * columns, 140 * lines), (columns, lines), 'RGB', (255, 255, 255))
                imw.draw_wall(list(self.__cats_anned.values()), list(self.__cats_anned.keys()))
                imw.draw_grids((0, 0, 0), 2)
                if show:imw.show_wall()
                if out:
                    if not os.path.exists(out):
                        os.makedirs(out)
                    imw.save(os.path.join(out, datetime.now().strftime('%m-%d_%H%M%S') + '.png'))

    def deepscores_to_doata(self, *annfiles, outdir):
        for f in annfiles:
            self.__assert_jsonfile(f)

        if not os.path.exists(outdir):  # 如果输出目录不存在，则创建该目录
            os.makedirs(outdir)

        for p in annfiles: 
            ob = OBBAnns(p)
            ob.load_annotations()
            ob.set_annotation_set_filter(['deepscores'])
            for i in tqdm(range(len(ob.img_info)), desc=f'正在转换文件{os.path.split(p)[1]}'):
                df = ob.get_anns(i)
                filename = ob.img_info[i]['filename']
                for j in range(len(df)):
                    with open(Path(outdir).joinpath(filename).with_suffix('.txt'), 'a+') as f:
                        ann =  df.iloc[j,]
                        content = ' '.join([str(k) for k in ann['o_bbox']])
                        content += ' '
                        content += ob.cat_info[ df.iloc[j,]['cat_id'][0]]['name']    
                        content += ' '
                        content += '0'
                        content += '\n'         
                        f.write(content)

    def get_cats(self, *annfiles, outfile, cats_anned=False):
        assert not os.path.exists(outfile),f'{outfile}文件已经存在，请先删除或使用别的名称'
        out_dir, file = os.path.split(outfile)
        assert (os.path.splitext(file)[1] in ['.txt', '.py']), '输出的文件格式必须是.txt或.py格式'
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        self.__get_cats_info(annfiles, cats_bbox=cats_anned)
        cats = self.__allcats if not cats_anned else self.__cats_anned
        with open(outfile, 'a+') as f:
            count = 0
            for k, v in cats.items():
                content = f"'{k}'" + ','
                f.write(content)
                count += 1
                if not count % 10:
                    f.write('\n')
            print(count)

    def visualize_annotation(self, annfile, out_dir=None, image=None):
        self.__assert_jsonfile(annfile)
        ob = OBBAnns(annfile)
        ob.load_annotations()
        max_size = len(ob.img_info)
        view = 0
        if image:
            for index, i in enumerate(ob.img_info):
                if image == i['filename']:
                    view = index
        kn = 0
        while True:
               ob.visualize(img_idx=view, out_dir = out_dir, show=True, instances=True)
               while kn not in ['up', 'down', 'left', 'right', 'esc']:kn = keyboard.read_key()
               if kn in ['up', 'left']:
                   view = 0 if view == 0 else view - 1 
               elif kn in ['down', 'right']:
                   view = max_size if view == max_size else view + 1
               else:
                   break
               kn = 0

if __name__=='__main__':
    ds2 = DeepScoresV2()
    ds2.get_cats('../../datasets/ds2_dense/deepscores_train.json', outfile='../out/cats.txt')